import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import rawpy
from PIL import Image, TiffImagePlugin
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from imaging import DETAIL_FIELDS, category, decode, metadata
from main import STYLE, Window


class MetadataTests(unittest.TestCase):
    def test_synthetic_dng_decodes_preview_and_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.dng"
            pixels = np.arange(128 * 128, dtype=np.uint16).reshape(128, 128)
            tags = TiffImagePlugin.ImageFileDirectory_v2()
            for key, value in {
                271: "Test",
                272: "Synthetic camera",
                262: 32803,
                33421: (2, 2),
                33422: bytes([0, 1, 1, 2]),
                50706: bytes([1, 4, 0, 0]),
                50707: bytes([1, 1, 0, 0]),
                50708: "Test synthetic camera",
                50717: 65535,
                50778: 21,
            }.items():
                tags[key] = value
            tags[50721] = tuple(
                TiffImagePlugin.IFDRational(v) for v in (1, 0, 0, 0, 1, 0, 0, 0, 1)
            )
            tags.tagtype[50721] = 10
            tags[50728] = tuple(TiffImagePlugin.IFDRational(1) for _ in range(3))
            tags.tagtype[50728] = 5
            Image.fromarray(pixels).save(path, format="TIFF", tiffinfo=tags)
            for preview in (True, False):
                image, details = decode(path, preview)
                self.assertGreater(image.width, 0)
                self.assertEqual(image.mode, "RGB")
                self.assertIn("128", details["Resolution"])
                self.assertEqual(details["Device"], "Test Synthetic camera")
            dump = path.with_suffix(".RAW")
            with rawpy.imread(str(path)) as raw:
                raw.raw_image.astype("<u2").tofile(dump)
            expected, _ = decode(path, False)
            actual, details = decode(dump, False)
            self.assertEqual(actual.tobytes(), expected.tobytes())
            self.assertEqual(details["Filename"], dump.name)
            self.assertEqual(details["File size"], metadata(dump, {})["File size"])
            # A changed dump must render its own pixels, not its companion's image.
            dump.write_bytes(bytes(dump.stat().st_size))
            for preview in (True, False):
                actual, _ = decode(dump, preview)
                self.assertEqual(actual.getextrema(), ((0, 0),) * 3)
            dump.write_bytes(bytes(dump.stat().st_size // 2))
            with self.assertRaisesRegex(ValueError, "byte size"):
                decode(dump)

    def test_headerless_raw_requires_companion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orphan.RAW"
            path.write_bytes(bytes(1024))
            with self.assertRaisesRegex(ValueError, "matching DNG"):
                decode(path)

    def test_categories(self):
        self.assertEqual(category("PHOTO.DNG"), "DNG")
        for name in ("a.RAW", "a.CR3", "a.nef", "a.ARW", "a.raf"):
            self.assertEqual(category(name), "RAW")
        self.assertIsNone(category("a.jpg"))

    def test_missing_fields(self):
        details = metadata("/missing/a.dng", {})
        self.assertEqual(details["Filename"], "a.dng")
        self.assertTrue(
            all(value == "N/A" for key, value in details.items() if key != "Filename")
        )

    def test_metadata_and_centimeter_resolution(self):
        tags = {
            "Image Make": "Camera",
            "Image Model": "Model",
            "EXIF DateTimeOriginal": "2026:09:05 12:30:00",
            "Image ResolutionUnit": SimpleNamespace(values=[3]),
            "Image XResolution": SimpleNamespace(values=[100]),
            "Image YResolution": SimpleNamespace(values=[100]),
        }
        result = metadata("/missing/a.dng", tags, (6000, 4000))
        self.assertEqual(result["DPI"], "254 × 254 DPI")
        self.assertEqual(result["Device"], "Camera Model")
        self.assertEqual(result["Resolution"], "6000 × 4000")
        self.assertEqual(result["Date taken"], "2026:09:05 12:30:00")

    def test_corrupt_file_is_not_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.dng"
            path.write_bytes(b"not a raw file")
            with self.assertRaises(Exception):
                decode(path)
            self.assertIn("14 bytes", metadata(path)["File size"])

    def test_exposure_and_color_details(self):
        tags = {
            "EXIF FNumber": "28/10", "EXIF ExposureTime": "1/125",
            "EXIF ISOSpeedRatings": "400", "EXIF FocalLength": "85",
            "EXIF FocalLengthIn35mmFilm": "127", "EXIF ExposureBiasValue": "-1/3",
            "EXIF LensModel": "85mm F2.8", "EXIF WhiteBalance": "Auto",
            "EXIF ExposureProgram": "Aperture Priority", "EXIF Flash": "Flash did not fire",
            "EXIF MeteringMode": "Pattern", "EXIF ColorSpace": "2",
            "Image BitsPerSample": SimpleNamespace(values=[14]),
            "Image PhotometricInterpretation": "32803",
        }
        result = metadata("/missing/photo.dng", tags)
        self.assertEqual(set(result), set(DETAIL_FIELDS))
        for field, expected in {
            "Aperture": "f/2.8", "Shutter speed": "1/125 s", "ISO": "400",
            "Focal length": "85 mm", "35mm equivalent": "127 mm",
            "Exposure compensation": "-0.33 EV", "Lens": "85mm F2.8",
            "White balance": "Auto", "Color space": "Adobe RGB",
            "Bits per sample": "14 bits", "Color encoding": "Color filter array (RAW)",
        }.items():
            self.assertEqual(result[field], expected)
        tags["EXIF ExposureTime"] = "5/2"
        tags["EXIF ExposureBiasValue"] = "0"
        result = metadata("/missing/photo.dng", tags)
        self.assertEqual(result["Shutter speed"], "2.5 s")
        self.assertEqual(result["Exposure compensation"], "+0.00 EV")

    def test_invalid_exposure_and_color(self):
        result = metadata("/missing/photo.dng", {
            "EXIF FNumber": "0/0", "EXIF ExposureTime": "-1",
            "EXIF ISOSpeedRatings": "NaN", "EXIF FocalLength": "0",
            "Image BitsPerSample": SimpleNamespace(values=["invalid"]),
            "EXIF ColorSpace": "65535",
        })
        for field in ("Aperture", "Shutter speed", "ISO", "Focal length", "Bits per sample"):
            self.assertEqual(result[field], "N/A")
        self.assertEqual(result["Color space"], "Uncalibrated")


class PictureTests(unittest.TestCase):
    def test_real_pictures_render_preview_and_photo(self):
        pictures = Path(__file__).parent / "pictures"
        files = sorted(p for p in pictures.rglob("*") if p.is_file() and category(p))
        if not files:
            self.skipTest("Place DNG / RAW fixtures in tests/pictures")
        for path in files:
            for preview in (True, False):
                with self.subTest(file=path.name, preview=preview):
                    image, details = decode(path, preview)
                    self.assertEqual(image.mode, "RGB")
                    self.assertGreater(min(image.size), 0)
                    self.assertLessEqual(max(image.size), 640 if preview else 6000)
                    self.assertTrue(any(low < high for low, high in image.getextrema()))
                    self.assertEqual(details["Filename"], path.name)
                    self.assertNotEqual(details["Resolution"], "N/A")


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = Window()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def wait_until(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(condition())

    def test_real_raw_import_thumbnail_and_viewer(self):
        path = Path(__file__).parent / "pictures" / "IMG_3834.RAW"
        if not path.is_file():
            self.skipTest("IMG_3834.RAW fixture is absent")
        self.window.import_paths([path, path.with_suffix(".DNG")])
        self.wait_until(lambda: len(self.window.files) == 2)
        self.window.tabs.setCurrentIndex(1)
        self.assertEqual(self.window.grid.count(), 1)
        key = str(path.resolve())
        self.wait_until(lambda: key in self.window.thumbnails or key in self.window.errors,
                        timeout=30)
        self.assertNotIn(key, self.window.errors)
        self.assertFalse(self.window.thumbnails[key].isNull())
        self.window.open_photo(self.window.grid.item(0))
        self.wait_until(lambda: self.window.viewer_status.text() != "Developing photo…",
                        timeout=30)
        self.assertNotIn("Could not decode", self.window.viewer_status.text())
        self.assertEqual(self.window.detail_labels["Filename"].text(), path.name)
        self.assertEqual(self.window.detail_labels["Resolution"].text(), "4032 × 3024")
        self.assertEqual(len(self.window.photo.scene().items()), 1)
        self.window.info.click()
        for suffix, tab in ((".DNG", 0), (".RAW", 1)):
            self.assertTrue(self.window.format_switch.isVisible())
            self.assertEqual(self.window.format_switch.text(), f"Switch to {suffix[1:]}")
            self.window.format_switch.click()
            self.assertEqual(self.window.current, str(path.with_suffix(suffix).resolve()))
            self.assertEqual(self.window.tabs.currentIndex(), tab)
            self.wait_until(lambda: self.window.viewer_status.text() != "Developing photo…",
                            timeout=30)
            self.assertNotIn("Could not decode", self.window.viewer_status.text())
            self.assertEqual(self.window.detail_labels["Filename"].text(), path.with_suffix(suffix).name)
            self.assertTrue(self.window.details_panel.isVisible())
            self.assertEqual(len(self.window.photo.scene().items()), 1)

    def test_format_switch_requires_unique_pair_in_same_folder(self):
        with patch.object(self.window, "submit"):
            self.window.files = ["/photos/a.DNG", "/other/a.RAW", "/photos/b.RAW"]
            self.window.populate()
            self.window.open_photo(self.window.grid.item(0))
            self.assertFalse(self.window.format_switch.isVisible())
            self.window.switch_format()
            self.assertEqual(self.window.current, "/photos/a.DNG")
            self.window.files += ["/photos/a.RAW", "/photos/a.NEF"]
            self.window.open_photo(self.window.grid.item(0))
            self.assertFalse(self.window.format_switch.isVisible())

    def test_developed_cache_reuses_twenty_pairs_and_evicts_whole_pair(self):
        image = QImage(60, 40, QImage.Format.Format_RGB888)
        image.fill(Qt.GlobalColor.darkGreen)

        def finish(key, function, callback, priority=0):
            callback(key, (image, metadata(key[1], {}, (60, 40))), None, None)

        self.window.timer.stop()
        self.window.files = [f"/photos/{i:02}.{suffix}"
                             for i in range(21) for suffix in ("DNG", "RAW")]
        self.window.populate()
        with patch.object(self.window, "submit", side_effect=finish) as submit:
            for index in range(20):
                self.window.open_photo(self.window.grid.item(index))
                self.window.format_switch.click()
                self.window.format_switch.click()
            self.assertEqual(submit.call_count, 40)
            self.assertEqual(len(self.window.developed), 20)
            self.assertEqual(sum(len(versions) for versions in self.window.developed.values()), 40)
            self.window.close_photo()
            self.window.open_photo(self.window.grid.item(0))
            self.window.format_switch.click()
            self.window.format_switch.click()
            self.assertEqual(submit.call_count, 40)
            self.assertEqual(self.window.detail_labels["Filename"].text(), "00.DNG")
            self.window.open_photo(self.window.grid.item(20))
            self.assertEqual(len(self.window.developed), 20)
            self.assertEqual(len(self.window.developed[Path("/photos/00")]), 2)
            self.assertNotIn(Path("/photos/01"), self.window.developed)
            self.window.open_photo(self.window.grid.item(1))
            self.window.format_switch.click()
            self.assertEqual(submit.call_count, 43)

    def test_cache_does_not_group_same_filename_in_different_folders(self):
        self.window.timer.stop()
        self.window.files = ["/one/a.DNG", "/two/a.DNG"]
        self.window.populate()
        with patch.object(self.window, "submit"):
            for index in (0, 1):
                self.window.open_photo(self.window.grid.item(index))
        self.assertEqual(len(self.window.developed), 2)

    def test_development_in_flight_is_reused_and_old_import_is_ignored(self):
        self.window.timer.stop()
        self.window.files = ["/photos/a.DNG", "/photos/b.DNG"]
        self.window.populate()
        image = QImage(60, 40, QImage.Format.Format_RGB888)
        image.fill(Qt.GlobalColor.darkGreen)
        with patch.object(self.window, "submit") as submit:
            for index in (0, 1, 0):
                self.window.open_photo(self.window.grid.item(index))
            self.assertEqual(submit.call_count, 2)
            first_key = submit.call_args_list[0].args[0]
            second_key = submit.call_args_list[1].args[0]
            result = (image, metadata(second_key[1], {}, (60, 40)))
            self.window.photo_loaded(second_key, result, None, None)
            self.assertEqual(self.window.current, first_key[1])
            self.window.open_photo(self.window.grid.item(1))
            self.assertEqual(submit.call_count, 2)
            self.window.import_paths([])
            self.window.photo_loaded(first_key, result, None, None)
            self.assertFalse(self.window.developed)

    def test_grid_columns_tabs_and_viewer(self):
        image = QImage(600, 400, QImage.Format.Format_RGB888)
        image.fill(Qt.GlobalColor.darkGreen)
        details = metadata("/missing/photo.dng", {}, (6000, 4000))
        with patch("main.load_image", return_value=(image, details)):
            self.window.files = [f"/missing/photo{i}.dng" for i in range(12)] + [
                "/missing/photo.nef"
            ]
            self.window.populate()
            self.assertEqual(self.window.grid.count(), 12)
            self.assertEqual(self.window.grid.columns, 4)
            for value, columns in ((1, 10), (10, 1), (7, 4)):
                self.window.slider.setValue(value)
                self.app.processEvents()
                self.assertEqual(self.window.grid.columns, columns)
                first = self.window.grid.visualItemRect(self.window.grid.item(0))
                last = self.window.grid.visualItemRect(
                    self.window.grid.item(columns - 1)
                )
                next_row = self.window.grid.visualItemRect(
                    self.window.grid.item(columns)
                )
                self.assertEqual(first.y(), last.y())
                self.assertGreater(next_row.y(), first.y())
            self.window.tabs.setCurrentIndex(1)
            self.assertEqual(self.window.grid.count(), 1)
            self.window.tabs.setCurrentIndex(0)
            self.window.open_photo(self.window.grid.item(0))
            self.wait_until(
                lambda: self.window.detail_labels["Resolution"].text() == "6000 × 4000"
            )
            self.assertEqual(self.window.stack.currentIndex(), 1)
            self.window.info.click()
            self.assertTrue(self.window.details_panel.isVisible())
            self.app.processEvents()
            self.assertGreater(self.window.details_panel.verticalScrollBar().maximum(), 0)
            self.assertEqual(set(self.window.detail_labels), set(DETAIL_FIELDS))
            self.assertEqual(self.window.detail_labels["DPI"].text(), "N/A")
            self.window.close_photo()
            self.assertEqual(self.window.stack.currentIndex(), 0)
            self.assertFalse(self.window.details_panel.isVisible())
            self.window.pool.waitForDone()
            self.app.processEvents()

    def test_folder_import_and_decode_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "broken.DNG").write_bytes(b"broken")
            (root / "nested" / "broken.NEF").write_bytes(b"broken")
            (root / "ignore.jpg").write_bytes(b"broken")
            self.window.import_paths([root])
            self.wait_until(lambda: len(self.window.files) == 2)
            self.assertEqual(self.window.grid.count(), 1)
            self.window.open_photo(self.window.grid.item(0))
            self.wait_until(
                lambda: "Could not decode" in self.window.viewer_status.text()
            )
            self.assertEqual(self.window.detail_labels["Device"].text(), "N/A")


if __name__ == "__main__":
    unittest.main()
