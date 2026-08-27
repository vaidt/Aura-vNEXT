"""Confidence conversion semantics (ADR-0005 section 5).

Confidence enters evidence as an integer count of basis points. The conversion is
part of the contract: if it were left to the producer, two producers could seal the
same stated confidence into two different digests.
"""

import unittest
from decimal import Decimal

from core.models import CONFIDENCE_SCALE, ModelError, Violation, confidence_to_basis_points


class RequiredVectorTest(unittest.TestCase):
    def test_the_four_required_conversions(self):
        for value, expected in ((0.0, 0), (0.5, 5000), (0.95, 9500), (1.0, 10000)):
            with self.subTest(value=value):
                self.assertEqual(expected, confidence_to_basis_points(value))

    def test_scale_is_ten_thousand(self):
        self.assertEqual(10000, CONFIDENCE_SCALE)
        self.assertEqual(CONFIDENCE_SCALE, confidence_to_basis_points(1.0))

    def test_binary_floating_point_artefacts_do_not_leak(self):
        """Naive binary scaling is wrong for 573 of the 10001 representable inputs.

        0.0003 * 10000 is 2.9999999999999996, which truncates to 2. Conversion goes
        through the shortest round-tripping decimal instead, so the answer is 3 by
        rule rather than by the accident of how a float landed.
        """
        self.assertEqual(2, int(0.0003 * CONFIDENCE_SCALE))
        self.assertEqual(3, confidence_to_basis_points(0.0003))

        divergent = [
            value / CONFIDENCE_SCALE
            for value in range(CONFIDENCE_SCALE + 1)
            if int((value / CONFIDENCE_SCALE) * CONFIDENCE_SCALE) != value
        ]
        self.assertTrue(divergent, "expected naive scaling to diverge somewhere")
        for value in divergent:
            with self.subTest(value=value):
                self.assertEqual(
                    round(value * CONFIDENCE_SCALE), confidence_to_basis_points(value)
                )

    def test_equivalent_spellings_agree(self):
        for spelling in (0.95, "0.95", "0.9500", Decimal("0.95")):
            with self.subTest(spelling=spelling):
                self.assertEqual(9500, confidence_to_basis_points(spelling))

    def test_integers_at_the_boundaries(self):
        self.assertEqual(0, confidence_to_basis_points(0))
        self.assertEqual(10000, confidence_to_basis_points(1))


class RoundingTest(unittest.TestCase):
    def test_ties_round_half_to_even(self):
        self.assertEqual(1234, confidence_to_basis_points("0.12345"))
        self.assertEqual(1236, confidence_to_basis_points("0.12355"))

    def test_rounding_is_stated_not_truncating(self):
        self.assertEqual(1235, confidence_to_basis_points("0.123456"))


class RejectionTest(unittest.TestCase):
    """Invalid values are rejected, never clamped.

    A clamped confidence would be sealed into evidence as though the producer had
    supplied it, which is precisely the silent approximation M0 forbids.
    """

    def test_non_finite_values_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ModelError):
                    confidence_to_basis_points(value)

    def test_out_of_range_values_are_rejected_not_clamped(self):
        for value in (-0.1, 1.1, -1, 2, "1.00001", Decimal("-0.0001")):
            with self.subTest(value=value):
                with self.assertRaises(ModelError):
                    confidence_to_basis_points(value)

    def test_non_numeric_values_are_rejected(self):
        for value in (None, "high", "", [], {}, object()):
            with self.subTest(value=value):
                with self.assertRaises(ModelError):
                    confidence_to_basis_points(value)

    def test_bool_is_not_a_confidence(self):
        """bool is a subclass of int; True must not become a confidence of 1.0."""
        for value in (True, False):
            with self.subTest(value=value):
                with self.assertRaises(ModelError):
                    confidence_to_basis_points(value)

    def test_a_violation_cannot_be_built_with_an_invalid_confidence(self):
        with self.assertRaises(ModelError):
            Violation.build("R", "BLOCK", float("nan"))
        with self.assertRaises(ModelError):
            Violation.build("R", "BLOCK", 1.5)


class RepresentationTest(unittest.TestCase):
    def test_violation_carries_integer_basis_points(self):
        violation = Violation.build("R", "BLOCK", 0.95)
        self.assertEqual(9500, violation.confidence)
        self.assertIsInstance(violation.confidence, int)
        self.assertEqual(9500, violation.canonical_representation()["confidence"])

    def test_out_of_range_basis_points_are_rejected_at_representation_time(self):
        """Bypassing build() must not smuggle an unrepresentable confidence through."""
        with self.assertRaises(ModelError):
            Violation(rule="R", action="BLOCK", confidence=10001).canonical_representation()
        with self.assertRaises(ModelError):
            Violation(rule="R", action="BLOCK", confidence=-1).canonical_representation()

    def test_float_confidence_cannot_reach_the_canonical_form(self):
        from core.canonical import CanonicalisationError, canonical_bytes
        with self.assertRaises(CanonicalisationError):
            canonical_bytes({"confidence": 0.95})


if __name__ == "__main__":
    unittest.main()
