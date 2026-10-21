import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bridge.state as state
from bridge.face import RANGES, compose
from bridge.head import _euler
from bridge.openxr_head import quat_to_matrix
from bridge.outputs.ifacial import packet
from bridge.outputs.vtube import parameter_payload, source_for
from bridge.update import is_newer
import bridge.settings as settings


def _reset_face():
    state.raw.clear()
    state.reset_outputs(RANGES)
    state.model_params = {}
    state.EYE_GAZE = 1.0
    state.EYE_REST = 0.5
    state.MOUTH_GAIN = 1.0
    state.SMILE_REST = 0.5
    state.BROW_GAIN = 1.0
    state.HEAD_GAIN = 0.4


class FaceTests(unittest.TestCase):
    def setUp(self):
        _reset_face()

    def test_mouth_and_gaze_follow_the_sliders(self):
        state.raw["JawOpen"] = 0.5
        state.raw["EyeLeftX"] = 0.5
        state.raw["EyeRightY"] = -0.25
        compose()
        self.assertAlmostEqual(state.outputs["MouthOpen"], 0.5)
        self.assertAlmostEqual(state.outputs["EyeLeftX"], 0.5)
        state.EYE_GAZE = 1.6
        state.MOUTH_GAIN = 1.8
        state.blink_seen["EyeOpenLeft"] = None
        state.blink_seen["EyeOpenRight"] = None
        compose()
        self.assertAlmostEqual(state.outputs["EyeLeftX"], 0.8)
        self.assertAlmostEqual(state.outputs["MouthOpen"], 0.9)

    def test_vts_aliases_scale_into_the_model_range(self):
        self.assertEqual(source_for("ParamMouthOpenY"), "MouthOpen")
        state.smooth["MouthOpen"] = 0.5
        state.model_params = {"ParamMouthOpenY": {"min": 0, "max": 100}}
        found = next(item for item in parameter_payload() if item["id"] == "ParamMouthOpenY")
        self.assertEqual(found["value"], 50)


class PacketTests(unittest.TestCase):
    def setUp(self):
        _reset_face()

    def test_head_order_is_pitch_yaw_roll(self):
        state.smooth["FaceAngleY"] = 10
        state.smooth["FaceAngleX"] = 20
        state.smooth["FaceAngleZ"] = 30
        state.smooth["MouthOpen"] = 1
        state.smooth["EyeOpenLeft"] = 0
        body = packet().decode()
        self.assertIn("=head#10.0000,20.0000,30.0000,", body)
        self.assertIn("jawOpen-100", body)
        self.assertIn("eyeBlink_L-100", body)
        self.assertIn("|rightEye#", body)
        self.assertIn("|leftEye#", body)


class HeadMathTests(unittest.TestCase):
    def test_identity_quaternion_and_euler(self):
        matrix = quat_to_matrix(0, 0, 0, 1)
        for row in range(3):
            for col in range(3):
                self.assertAlmostEqual(matrix[row][col], 1.0 if row == col else 0.0)
        self.assertEqual(_euler(matrix), (0.0, 0.0, 0.0))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings.PATH = os.path.join(self.tmp.name, "bridge_settings.json")
        state.loaded = False
        state.status["output"] = "Waiting for VTube Studio"
        settings.load()

    def tearDown(self):
        settings.PATH = None
        state.loaded = False
        self.tmp.cleanup()

    def test_switch_remembers_each_sides_sliders(self):
        self.assertEqual(state.destination, "vts")
        self.assertEqual(state.HEAD_GAIN, 0.4)
        self.assertFalse(state.INVERT_YAW)
        self.assertEqual(state.SMOOTH_FACE, 0.85)
        state.HEAD_GAIN = 0.25
        settings.set_destination("ifm")
        self.assertEqual(state.HEAD_GAIN, 1.0)
        self.assertTrue(state.INVERT_YAW)
        self.assertTrue(state.INVERT_PITCH)
        self.assertEqual(state.SMOOTH_FACE, 1.0)
        self.assertEqual(state.TICK, 0.016)
        self.assertEqual(state.status["output"], "Waiting for iFacialMocap")
        settings.set_destination("vts")
        self.assertEqual(state.HEAD_GAIN, 0.25)
        self.assertFalse(state.INVERT_YAW)
        self.assertEqual(state.SMOOTH_FACE, 0.85)
        state.loaded = False
        settings.load()
        self.assertEqual(state.destination, "vts")
        self.assertEqual(state.HEAD_GAIN, 0.25)


class UpdateTests(unittest.TestCase):
    def test_only_a_higher_release_counts(self):
        self.assertTrue(is_newer("v1.2.0", "1.0.0"))
        self.assertTrue(is_newer("1.0.1", "v1.0.0"))
        self.assertFalse(is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(is_newer("0.9.0", "1.0.0"))
        self.assertFalse(is_newer("latest", "1.0.0"))


if __name__ == "__main__":
    unittest.main()
