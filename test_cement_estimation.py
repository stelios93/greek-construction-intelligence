#!/usr/bin/env python3
"""
Unit tests for cement estimation model.
Based on 20 randomly sampled permits, independently estimated by a civil engineer.

Each test checks that our model's estimate is within an acceptable tolerance
of the expert estimate. Tolerance rules:
  - If expert says 0t: our estimate must be <= 0.5t
  - If expert says < 1t: our estimate must be within 0.5t
  - If expert says >= 1t: our estimate must be within 50% or 2t, whichever is larger
"""
import pytest
from titan_v2 import classify_and_estimate

# (subject, expert_cement_t, expert_reason)
PERMIT_CASES = [
    (
        "Οικοδομική Άδεια (ν.4759/2020): ΝΕΑ ΙΣΟΓΕΙΑ ΑΓΡΟΤΙΚΗ ΑΠΟΘΗΚΗ",
        3.0,
        "New single-story agricultural storage ~80-100m². Slab foundation + minimal walls. ~10m³ concrete.",
    ),
    (
        "Αναθεώρηση Έγκρισης Εργασιών Δόμησης Μικρής Κλίμακας: τοποθέτηση εξωτερικής θερμομόνωσης στις εξωτερικές όψεις",
        0.0,
        "External thermal insulation. No concrete work.",
    ),
    (
        "Ενημέρωση Οικοδομικής Αδείας (ν.4759/2020): ΕΝΗΜΕΡΩΣΗ ΤΗΣ 1824746/2026 ΓΙΑ ΣΥΜΠΛΗΡΩΣΗ ΑΡΙΘΜΗΤΙΚΩΝ ΣΤΟΙΧΕΙΩΝ ΣΤΙΣ ΚΑΤΟΨΕΙΣ",
        0.0,
        "Administrative update — adding missing data to floor plans. No construction.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: Ε.Ε.Δ.Μ.Κ ΓΙΑ ΑΛΛΑΓΗ ΧΡΗΣΗΣ ΑΠΟ ΚΑΤΑΣΤΗΜΑ ΣΕ ΕΠΑΓΓΕΛΜΑΤΙΚΟ ΕΡΓΑΣΤΗΡΙΟ",
        0.0,
        "Change of use from shop to workshop. Paperwork only, no structural concrete.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΓΚΡΙΣΗ ΕΡΓΑΣΙΩΝ ΔΟΜΗΣΗΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ ΓΙΑ ΤΟΠΟΘΕΤΗΣΗ ΕΞΩΤΕΡΙΚΗΣ ΘΕΡΜΟΜΟΝΩΣΗΣ",
        0.0,
        "External thermal insulation only. No concrete.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: Κατασκευή θερμομόνωσης εξωτερικής τοιχοποιίας περιμετρικά της μονοκατοικίας",
        0.0,
        "Perimeter insulation on a house. No concrete work.",
    ),
    (
        "Ενημέρωση Οικοδομικής Αδείας (ν.4759/2020): Β΄ ΕΝΗΜΕΡΩΣΗ ΓΙΑ ΑΛΛΑΓΗ ΟΨΕΩΝ ΚΑΙ ΔΙΑΜΟΡΦΩΣΕΩΝ ΠΕΡΙΒΑΛΛΟΝΤΟΣ ΧΩΡΟΥ",
        0.0,
        "Administrative update for facade changes and landscaping. No new construction.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΡΓΑΣΙΕΣ ΕΓΚΑΤΑΣΤΑΣΗΣ ΑΥΤΟΝΟΜΟΥ ΣΥΣΤΗΜΑΤΟΣ ΘΕΡΜΑΝΣΗΣ ΔΙΑΜΕΡΙΣΜΑΤΟΣ Γ-1 ΤΟΥ ΤΡΙΤΟΥ ΟΡΟΦΟΥ",
        0.0,
        "Installing heating system in apartment. Mechanical work, no concrete.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΡΓΑΣΙΕΣ ΤΟΠΟΘΕΤΗΣΗΣ ΕΞΩΤΕΡΙΚΗΣ ΘΕΡΜΟΜΟΝΩΣΗΣ ME ΧΡΗΣΗ ΙΚΡΙΩΜΑΤΩΝ & ΒΕΒΑΙΩΣΗ ΤΗΡΗΣΗΣ ΚΤΙΡΙΟΔΟΜΙΚΟΥ ΚΑΝΟΝΙΣΜΟΥ",
        0.0,
        "External insulation with scaffolding. No concrete.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: AΔΕΙΑ EΓΚΡΙΣΗΣ ΕΡΓΑΣΙΩΝ ΔΟΜΗΣΗΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ ΓΙΑ ΕΣΩΤΕΡΙΚΕΣ ΔΙΑΡΡΥΘΜΙΣΕΙΣ (ΚΑΤΟΙΚΙΑΣ) ΤΟΥ ΤΕΤΑΡΤΟΥ ΠΑΝΩ ΑΠΟ ΤΟ ΙΣΟΓΕΙΟ ΟΡΟΦΟΥ",
        0.3,
        "Internal rearrangements on 4th floor. Possible light partition walls needing small mortar.",
    ),
    (
        "Οικοδομική Άδεια (ν.4759/2020): ΕΣΩΤΕΡΙΚΕΣ ΔΙΑΡΡΥΘΜΙΣΕΙΣ, ΕΣΩΤΕΡΙΚΟΙ ΧΡΩΜΑΤΙΣΜΟΙ, ΑΛΛΑΓΗ ΧΡΗΣΗΣ ΤΟΥ ΙΣΟΓΕΙΟΥ ΑΠΟ ΚΑΤΑΣΤΗΜΑ",
        0.3,
        "Internal rearrangements, painting, change of use at ground floor. Minor mortar for partitions.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΓΚΡΙΣΗ ΕΡΓΑΣΙΩΝ ΔΟΜΗΣΗΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ ΓΙΑ ΤΟΠΟΘΕΤΗΣΗ ΠΕΡΙΦΡΑΞΗΣ ΣΕ ΟΙΚΟΠΕΔΟ",
        0.5,
        "Fence on a plot. Small concrete footings for fence posts.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΡΓΑΣΙΕΣ ΣΤΗΝ ΟΡΙΖΟΝΤΙΑ ΙΔΙΟΚΤΗΣΙΑ Β-1 ΤΟΥ 2ΟΥ ΑΝΩ ΤΟΥ ΙΣΟΓΕΙΟΥ ΟΡΟΦΟΥ",
        0.3,
        "Works on 2nd floor horizontal property unit. Likely internal modifications.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΔΙΑΧΩΡΙΣΜΟΣ ΤΗΣ ΟΡΙΖΟΝΤΙΑΣ ΙΔΙΟΚΤΗΣΙΑΣ (ΚΑΤΟΙΚΙΑΣ) ΤΟΥ ΔΕΥΤΕΡΟΥ ΠΑΝΩ ΑΠΟ ΤΟ ΙΣΟΓΕΙΟ ΟΡΟΦΟΥ",
        0.3,
        "Splitting 2nd floor apartment into two. New partition wall(s), minor patching.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: Κατασκυη περγκολας.",
        0.5,
        "Building a pergola. Small concrete footings for posts.",
    ),
    (
        "Οικοδομική Άδεια (ν.4759/2020): Εσωτερικές διαρρυθμίσεις, χρωματισμοί, επεμβάσεις και επισκευή στις όψεις με χρήση ικριωμάτων",
        0.2,
        "Internal rearrangements, painting, facade repair. Mostly cosmetic, minor render patching.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας για εργασίες που αφορούν το πρόγραμμα Εξοικονομώ",
        0.0,
        "Energy efficiency (Exoikonomo) program — insulation, windows, boiler. No concrete.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΚΔΟΣΗ ΑΔΕΙΑΣ ΜΙΚΡΗΣ ΚΛΙΜΑΚΑΣ ΓΙΑ ΛΕΙΤΟΥΡΓΙΚΗ ΣΥΝΕΝΩΣΗ ΚΑΙ ΑΛΛΑΓΗ ΧΡΗΣΗΣ ΣΕ ΙΣΟΓΕΙΟ",
        0.2,
        "Functional merge + change of use on ground floor. Possibly removing/adding a partition.",
    ),
    (
        "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: Τοποθέτηση εξωτερικής θερμομόνωσης κελύφους, μόνωσης κάτω από μη θερμομονωμένη στέγη",
        0.0,
        "External shell insulation + under-roof insulation. No concrete.",
    ),
    (
        "Αναθεώρηση Έγκρισης Εργασιών Δόμησης Μικρής Κλίμακας: ΕΣΩΤΕΡΙΚΕΣ ΔΙΑΡΡΥΘΜΙΣΕΙΣ ΔΙΑΜΕΡΙΣΜΑΤΟΣ 4ου ΟΡΟΦΟΥ & ΤΡΟΠΟΠΟΙΗΣΗ ΑΝΟΙΓΜΑΤΩΝ",
        0.3,
        "Internal rearrangements in 4th floor apartment + modifying openings. Lintels/patching.",
    ),
]


def within_tolerance(our_estimate, expert_estimate):
    """Check if our estimate is acceptably close to expert estimate."""
    if expert_estimate == 0:
        return our_estimate <= 0.5
    elif expert_estimate < 1.0:
        return abs(our_estimate - expert_estimate) <= 0.5
    else:
        # Within 50% or 2t, whichever is larger
        tolerance = max(expert_estimate * 0.5, 2.0)
        return abs(our_estimate - expert_estimate) <= tolerance


@pytest.mark.parametrize(
    "subject, expert_t, reason",
    PERMIT_CASES,
    ids=[f"permit_{i+1}" for i in range(len(PERMIT_CASES))],
)
def test_cement_estimate(subject, expert_t, reason):
    result = classify_and_estimate(subject)
    our_t = result["cement_tonnes"]
    msg = (
        f"\n  Subject: {subject[:80]}..."
        f"\n  Expert: {expert_t}t ({reason[:60]})"
        f"\n  Ours:   {our_t}t"
        f"\n  Stage={result['stage']}, Con={result['construction']}, "
        f"Use={result['use']}, Floors={result['floors']}"
    )
    assert within_tolerance(our_t, expert_t), f"Estimate too far off!{msg}"


# Additional regression tests for specific known cases
class TestRegressions:
    def test_internal_rearrangements_apartment_not_high_cement(self):
        """The bug that started this: 5th floor apartment rearrangement was estimated at 24.8t"""
        r = classify_and_estimate(
            "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΡΓΑΣΙΕΣ ΕΣΩΤΕΡΙΚΩΝ ΔΙΑΡΡΥΘΜΙΣΕΩΝ ΣΕ ΔΙΑΜΕΡΙΣΜΑ 5ου ΟΡΟΦΟΥ"
        )
        assert r["cement_tonnes"] <= 0.5, f"Internal apartment rearrangement should need minimal cement, got {r['cement_tonnes']}t"
        assert r["floors"] == 0 or r["floors"] == 1, f"'5ου ΟΡΟΦΟΥ' should NOT be parsed as 5 floors, got {r['floors']}"

    def test_new_build_multi_story_reasonable(self):
        """A new multi-story residential should be 20-40t"""
        r = classify_and_estimate("Οικοδομική Άδεια: ΑΝΕΓΕΡΣΗ ΠΟΛΥΩΡΟΦΟΥ ΟΙΚΟΔΟΜΗΣ ΚΑΤΟΙΚΙΩΝ")
        assert 15 <= r["cement_tonnes"] <= 50, f"Multi-story new build should be 15-50t, got {r['cement_tonnes']}t"

    def test_new_2story_house_reasonable(self):
        """A new 2-story house should be 6-15t"""
        r = classify_and_estimate("Οικοδομική Άδεια: ΑΝΕΓΕΡΣΗ ΔΙΩΡΟΦΗΣ ΚΑΤΟΙΚΙΑΣ")
        assert 5 <= r["cement_tonnes"] <= 15, f"2-story house should be 5-15t, got {r['cement_tonnes']}t"

    def test_insulation_zero_cement(self):
        """Insulation work should need zero cement"""
        r = classify_and_estimate("Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΤΟΠΟΘΕΤΗΣΗ ΕΞΩΤΕΡΙΚΗΣ ΘΕΡΜΟΜΟΝΩΣΗΣ")
        assert r["cement_tonnes"] == 0.0, f"Insulation should be 0t, got {r['cement_tonnes']}t"

    def test_administrative_update_zero(self):
        """Administrative updates should always be 0t"""
        r = classify_and_estimate("Ενημέρωση Οικοδομικής Αδείας: ΕΝΗΜΕΡΩΣΗ ΓΙΑ ΑΛΛΑΓΗ ΟΨΕΩΝ")
        assert r["cement_tonnes"] == 0.0, f"Update should be 0t, got {r['cement_tonnes']}t"

    def test_fencing_zero_cement(self):
        """Fencing should be zero cement"""
        r = classify_and_estimate("Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΤΟΠΟΘΕΤΗΣΗ ΠΕΡΙΦΡΑΞΗΣ")
        assert r["cement_tonnes"] == 0.0, f"Fencing should be 0t, got {r['cement_tonnes']}t"

    def test_change_of_use_near_zero(self):
        """Change of use should be near-zero cement"""
        r = classify_and_estimate("Οικοδομική Άδεια: ΑΛΛΑΓΗ ΧΡΗΣΗΣ ΑΠΟ ΚΑΤΑΣΤΗΜΑ ΣΕ ΓΡΑΦΕΙΟ")
        assert r["cement_tonnes"] <= 0.5, f"Change of use should be ≤0.5t, got {r['cement_tonnes']}t"

    def test_exoikonomo_zero(self):
        """Exoikonomo (energy efficiency) program should be 0t"""
        r = classify_and_estimate(
            "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: εργασίες στο πλαίσιο του προγράμματος Εξοικονομώ"
        )
        assert r["cement_tonnes"] == 0.0, f"Exoikonomo should be 0t, got {r['cement_tonnes']}t"

    def test_heating_installation_near_zero(self):
        """Heating system installation should need no concrete"""
        r = classify_and_estimate(
            "Έγκριση Εργασιών Δόμησης Μικρής Κλίμακας: ΕΓΚΑΤΑΣΤΑΣΗ ΑΥΤΟΝΟΜΟΥ ΣΥΣΤΗΜΑΤΟΣ ΘΕΡΜΑΝΣΗΣ"
        )
        assert r["cement_tonnes"] <= 0.5, f"Heating installation should be ≤0.5t, got {r['cement_tonnes']}t"
