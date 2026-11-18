"""Tests for QuantumPhaseTransition-Lab: ED, JW, gaps, classifier, gates."""
import math

import pytest

import main as m


# ---- linear algebra + Hamiltonian construction
def test_kron_with_identity():
    a = [[1.0, 2.0], [3.0, 4.0]]
    out = m.kron(a, m.I2)
    assert out[0][0] == 1.0 and out[0][2] == 2.0 and out[3][3] == 4.0


def test_site_operator_sigma_x_flips_bit():
    # sigma_x on site 0 of a 2-spin chain maps |00> to |10> (index 2)
    op = m.site_operator(m.SIGMA_X, 0, 2)
    col = [op[r][0] for r in range(4)]
    assert col == [0.0, 0.0, 1.0, 0.0]


def test_hamiltonian_symmetric_and_traceless():
    ham = m.build_hamiltonian(5, 1.0, 0.5)
    assert all(abs(ham[i][j] - ham[j][i]) < 1e-12
               for i in range(32) for j in range(32))
    assert abs(sum(ham[i][i] for i in range(32))) < 1e-9


def test_jacobi_known_2x2():
    ev, _ = m.jacobi_eigh([[2.0, 1.0], [1.0, 2.0]])
    assert abs(min(ev) - 1.0) < 1e-10 and abs(max(ev) - 3.0) < 1e-10


def test_jacobi_reconstruction_n4():
    ham = m.build_hamiltonian(4, 1.0, 0.7)
    ev, v = m.jacobi_eigh(ham)
    err = 0.0
    for i in range(16):
        for j in range(16):
            s = sum(v[i][k] * ev[k] * v[j][k] for k in range(16))
            err = max(err, abs(s - ham[i][j]))
    assert err < 1e-9


# ---- exact diagonalization anchors
def test_ed_zero_field():
    r = m.ed_result(6, 0.0)
    assert abs(r["ground_energy_per_site"] + 1.0) < 1e-9
    assert abs(r["abs_magnetization"] - 1.0) < 1e-9
    assert r["spectral_gap"] < 1e-8


def test_ed_large_field_energy():
    assert abs(m.ed_result(5, 10.0)["ground_energy_per_site"] + 10.0) < 0.1


def test_ed_absmz_decreases_across_transition():
    scan = {row["g"]: row for row in m.ed_scan_report(6)}
    assert (scan[0.5]["abs_magnetization"] > scan[1.0]["abs_magnetization"]
            > scan[2.0]["abs_magnetization"])


# ---- Jordan-Wigner engine
def test_dispersion_endpoints():
    assert abs(m.dispersion(0.0, 0.5) - 1.0) < 1e-12
    assert abs(m.dispersion(math.pi, 0.5) - 3.0) < 1e-12
    assert abs(m.dispersion(0.0, 1.0)) < 1e-12


def test_jw_energy_anchors():
    assert abs(m.jw_ground_energy_per_site(0.0) + 1.0) < 1e-9
    assert abs(m.jw_ground_energy_per_site(1.0) + 4.0 / math.pi) < 1e-6


def test_jw_gap_formula():
    assert abs(m.jw_gap(0.5) - 1.0) < 1e-12
    assert m.jw_gap(1.0) == 0.0
    assert abs(m.jw_gap(1.5) - 1.0) < 1e-12


def test_jw_finite_fermion_gap_critical():
    for n in m.FINITE_N:
        assert abs(m.jw_finite_fermion_gap(n, 1.0)
                   - 4.0 * math.sin(math.pi / (2.0 * n))) < 1e-9


def test_jw_finite_matches_ed():
    for n in m.FINITE_N:
        for g in m.FINITE_G:
            assert abs(m.ed_result(n, g)["ground_energy_per_site"]
                       - m.jw_finite_energy_per_site(n, g)) < 1e-6


def test_ed_approaches_thermodynamic_limit():
    fs = {(r["g"], r["n"]): r for r in m.finite_size_report()}
    assert (fs[(0.5, 7)]["ed_minus_jw_thermo"]
            < fs[(0.5, 5)]["ed_minus_jw_thermo"] < 5e-3)
    assert (fs[(1.0, 7)]["ed_minus_jw_thermo"]
            < fs[(1.0, 5)]["ed_minus_jw_thermo"] < 0.025)


# ---- the two gap stories
def test_critical_gap_scaling():
    crit = m.gap_report()["critical_scaling"]
    assert all(1.5 < row["gap_times_n"] < 1.65 for row in crit)
    assert all(crit[i]["ed_gap_at_criticality"]
               > crit[i + 1]["ed_gap_at_criticality"]
               for i in range(len(crit) - 1))


def test_tunnelling_gap_collapses():
    tun = m.gap_report()["ordered_tunnelling"]
    assert all(tun[i + 1]["ed_gap_at_g_half"] < 0.6 * tun[i]["ed_gap_at_g_half"]
               for i in range(len(tun) - 1))


def test_disordered_gap_tracks_quasiparticle():
    for row in m.gap_report()["disordered_side"]:
        if row["g"] >= 1.5:
            assert (row["jw_quasiparticle_gap"] < row["ed_gap_n6"]
                    < 1.1 * row["jw_quasiparticle_gap"])


# ---- order parameter + correlation length
def test_yang_magnetization():
    assert m.yang_magnetization(0.0) == 1.0
    assert abs(m.yang_magnetization(0.5) - 0.75 ** 0.125) < 1e-12
    assert m.yang_magnetization(1.0) == 0.0
    assert m.yang_magnetization(1.5) == 0.0


def test_ed_absmz_approaches_yang():
    fs = {(r["g"], r["n"]): r for r in m.finite_size_report()}
    yang = m.yang_magnetization(0.5)
    assert (abs(fs[(0.5, 7)]["ed_abs_magnetization"] - yang)
            < abs(fs[(0.5, 5)]["ed_abs_magnetization"] - yang))


def test_correlation_length_proxy():
    assert abs(m.correlation_length(0.5) - 2.0) < 1e-12
    assert abs(m.correlation_length(0.9) - 10.0) < 1e-9
    assert m.correlation_length(1.0) == float("inf")
    assert m.correlation_length(0.99) > m.correlation_length(0.9)


# ---- classifier
def test_classifier_scenarios():
    rep = m.classifier_report()
    assert rep["deep_ordered_g0.30"] == "ordered"
    assert rep["ordered_g0.80"] == "ordered"
    assert rep["critical_g1.00"] == "critical-region"
    assert rep["disordered_g1.20"] == "disordered"
    assert rep["deep_disordered_g1.80"] == "disordered"


def test_classifier_matches_policy():
    for g in (0.3, 0.8, 1.0, 1.2, 1.8):
        assert (m.classify_phase(g, m.yang_magnetization(g), m.jw_gap(g))
                == m.phase_label(g, m.yang_magnetization(g), m.jw_gap(g)))


# ---- gates + seats + CLI
def test_hold_gates_14():
    assert len(m.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in m.HOLD_GATES.values())


@pytest.mark.parametrize("action", [
    "unsolved_model_solution_claim",
    "real_material_prediction_claim",
    "superconductor_design_claim",
    "quantum_hardware_result_claim",
    "criticality_sensor_claim",
    "financial_tipping_point_claim",
    "climate_tipping_point_claim",
    "thermodynamic_limit_overclaim",
])
def test_gates_hold(action):
    assert m.gate(action) == "HOLD"


def test_gate_sandbox_proceeds():
    assert m.gate("run_simulation") == "PROCEED"


def test_hold_demo_exits_2():
    assert m.main(["hold-demo"]) == 2
    assert m.main(["hold-demo", "run_simulation"]) == 0


def test_seats_never_override():
    brains = m.brains_report()
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["decider"]["can_override_hold"] is False
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_jw_deterministic():
    assert (m.jw_ground_energy_per_site(0.5)
            == m.jw_ground_energy_per_site(0.5))
    assert (m.jw_finite_energy_per_site(7, 1.0)
            == m.jw_finite_energy_per_site(7, 1.0))


def test_checks_all_pass():
    checks = m.run_checks()
    assert all(ok for _, ok in checks), [n for n, ok in checks if not ok]
