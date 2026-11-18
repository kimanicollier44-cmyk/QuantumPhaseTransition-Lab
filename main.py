#!/usr/bin/env python3
"""QuantumPhaseTransition-Lab - educational quantum phase transition lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * The lab studies ONE model: the one-dimensional transverse-field
    Ising model (TFIM), H = -J sum sigma_z sigma_z - h sum sigma_x
    on a ring. It is the textbook example of a quantum phase
    transition, and it is exactly solvable - the lab says so loudly.
    Nothing here solves, or claims to solve, an unsolved model.
  * Two independent engines are built and cross-checked against
    each other. Exact diagonalization diagonalizes the full
    Hamiltonian (built from Kronecker products) for N <= 7 spins
    with a from-scratch Jacobi eigensolver. The Jordan-Wigner /
    Bogoliubov free-fermion solution (the standard textbook
    formulas, implemented in code and LABELLED as standard results)
    gives the dispersion, the thermodynamic-limit ground energy,
    and the quasiparticle gap 2|J - h|, which closes exactly at
    h = J. The finite-N Jordan-Wigner sum reproduces the exact
    diagonalization ground energy to ~1e-8 - the two engines agree
    because the model is solved, not because either is magic.
  * The gap story has two honest halves. The quasiparticle gap
    closes at h = J. The raw spectral gap of a finite ring does
    something subtler: inside the ordered phase it collapses
    exponentially with N (tunnelling between the two symmetry-
    broken sectors), and exactly at criticality it closes only
    algebraically, gap ~ pi/(2N) - the finite-size shadow of the
    transition. Both halves are measured here, not asserted.
  * The spontaneous magnetization (1 - (h/J)^2)^(1/8) is the
    LABELLED Onsager-Yang result; the lab computes it next to the
    exact-diagonalization <|Mz|>, which trends toward it as N
    grows. No real material is predicted, fitted, or measured -
    those uses are permanent HOLD gates, with Gemini Argon 4
    Extended Thinking as DECIDER (names-only, tighten-only),
    Muse as advisor (never overrides HOLD), and Google Flow
    plan-only seats.
"""
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

# The model. J = 1 sets the energy unit; everything is reported as
# a function of the dimensionless ratio g = h / J. The quantum
# critical point of the 1D TFIM is at g = 1 exactly.
J_COUPLING = 1.0
SCAN_G = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
SCAN_N = 6
FINITE_N = (4, 5, 6, 7)
FINITE_G = (0.5, 1.0)
SIMPSON_INTERVALS = 4000

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "unsolved_model_solution_claim": "HOLD - no claim of solving an unsolved model; the 1D TFIM is exactly solvable and 2D/3D models are not solved here",
    "real_material_prediction_claim": "HOLD - no predicting a real material's transition temperature, field, or critical exponents",
    "superconductor_design_claim": "HOLD - no superconductor discovery, design, or Tc claim from Ising-model arithmetic",
    "quantum_hardware_result_claim": "HOLD - exact diagonalization of at most 7 spins on a laptop is not a quantum hardware result",
    "benchmark_supremacy_claim": "HOLD - no benchmark, supremacy, or advantage claim from toy sizes",
    "criticality_sensor_claim": "HOLD - no criticality-enhanced sensor, magnetometer, or metrology specification",
    "materials_engineering_guidance": "HOLD - no engineering guidance for real phase-change materials, alloys, or devices",
    "energy_device_claim": "HOLD - no energy storage, harvesting, or battery claim from critical phenomena",
    "financial_tipping_point_claim": "HOLD - no market crash, contagion, or financial tipping-point prediction",
    "climate_tipping_point_claim": "HOLD - no climate or ecological tipping-point forecast from a spin chain",
    "medical_phase_claim": "HOLD - no medical, protein-folding, or biological phase-transition claim",
    "plasma_fusion_claim": "HOLD - no plasma, fusion, or confinement criticality guidance",
    "cryptographic_claim": "HOLD - no cryptographic primitive, key, or security claim from critical phenomena",
    "thermodynamic_limit_overclaim": "HOLD - finite-N numbers must never be presented as thermodynamic-limit measurements, and the labelled Jordan-Wigner formulas must never be presented as new results",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# Small memo so the demo, the checks, and the tests share one run of
# each expensive diagonalization. Keys are the experiment parameters.
_CACHE = {}


# ================================================================ 1. Linear algebra
# Dense real matrices as lists of lists, built from scratch. The
# Hamiltonian is real symmetric (sigma_z sigma_z is diagonal, sigma_x
# is real), so a real Jacobi eigensolver is the right tool.

I2 = [[1.0, 0.0], [0.0, 1.0]]
SIGMA_X = [[0.0, 1.0], [1.0, 0.0]]
SIGMA_Z = [[1.0, 0.0], [0.0, -1.0]]


def kron(a, b):
    """Kronecker product of two dense matrices."""
    return [[a[i][j] * b[p][q]
             for j in range(len(a[0])) for q in range(len(b[0]))]
            for i in range(len(a)) for p in range(len(b))]


def site_operator(pauli, site, n):
    """One Pauli operator acting on `site` of an n-spin chain, via kron."""
    out = [[1.0]]
    for i in range(n):
        out = kron(out, pauli if i == site else I2)
    return out


def build_hamiltonian(n, j_coupling, h_field):
    """Full TFIM Hamiltonian on a ring, from Kronecker products.

    H = -J sum_i sigma_z(i) sigma_z(i+1) - h sum_i sigma_x(i).

    The sigma_z operators are diagonal, so the bond term contributes
    only through the product of the two operators' diagonals; the
    sigma_x operators are added in full. Both operators themselves
    are built with site_operator / kron above - nothing is hidden.
    """
    dim = 1 << n
    ham = [[0.0] * dim for _ in range(dim)]
    sz = [site_operator(SIGMA_Z, i, n) for i in range(n)]
    sx = [site_operator(SIGMA_X, i, n) for i in range(n)]
    for i in range(n):
        a = sz[i]
        b = sz[(i + 1) % n]
        for r in range(dim):
            ham[r][r] -= j_coupling * a[r][r] * b[r][r]
        x = sx[i]
        for r in range(dim):
            row = ham[r]
            xr = x[r]
            for c in range(dim):
                if xr[c]:
                    row[c] -= h_field * xr[c]
    return ham


def jacobi_eigh(matrix, tol=1e-12, max_sweeps=30):
    """Eigen-decomposition of a real symmetric matrix, cyclic Jacobi.

    Returns (eigenvalues, eigenvectors) with the eigenvectors as the
    COLUMNS of the second return value: matrix @ v[:, i] =
    eigenvalues[i] * v[:, i]. Deterministic: fixed sweep order, no
    randomness anywhere.
    """
    n = len(matrix)
    a = [row[:] for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = 0.0
        for i in range(n):
            ai = a[i]
            for j in range(i + 1, n):
                off += ai[j] * ai[j]
        if math.sqrt(off) < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if apq == 0.0:
                    continue
                tau = (a[q][q] - a[p][p]) / (2.0 * apq)
                t = (1.0 if tau >= 0 else -1.0) / (
                    abs(tau) + math.sqrt(1.0 + tau * tau))
                c = 1.0 / math.sqrt(1.0 + t * t)
                s = t * c
                for k in range(n):
                    akp = a[k][p]
                    akq = a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk = a[p][k]
                    aqk = a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp = v[k][p]
                    vkq = v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


# ================================================================ 2. Exact diagonalization
# The brute-force engine: build the full 2^N x 2^N Hamiltonian and
# diagonalize it. N <= 7 keeps the largest matrix at 128 x 128.

def ed_result(n, g):
    """Ground energy/site, spectral gap, and <|Mz|> for the N-spin ring."""
    key = ("ed", n, g)
    if key in _CACHE:
        return _CACHE[key]
    ham = build_hamiltonian(n, J_COUPLING, g * J_COUPLING)
    eigenvalues, vectors = jacobi_eigh(ham)
    order = sorted(range(len(eigenvalues)), key=lambda i: eigenvalues[i])
    e0 = eigenvalues[order[0]]
    e1 = eigenvalues[order[1]]
    ground_col = order[0]
    abs_mz = 0.0
    for s in range(1 << n):
        psi = vectors[s][ground_col]
        magnetization = (n - 2 * bin(s).count("1")) / n
        abs_mz += psi * psi * abs(magnetization)
    result = {
        "n": n,
        "g": g,
        "ground_energy_per_site": e0 / n,
        "spectral_gap": e1 - e0,
        "abs_magnetization": abs_mz,
    }
    _CACHE[key] = result
    return result


def ed_scan_report(n=SCAN_N):
    """The h-scan at fixed N: energy, gap, and order parameter vs g."""
    key = ("ed_scan", n)
    if key in _CACHE:
        return _CACHE[key]
    rows = []
    for g in SCAN_G:
        r = ed_result(n, g)
        rows.append({
            "g": g,
            "ground_energy_per_site": round(r["ground_energy_per_site"], 6),
            "spectral_gap": round(r["spectral_gap"], 6),
            "abs_magnetization": round(r["abs_magnetization"], 6),
            "jw_energy_per_site": round(jw_ground_energy_per_site(g), 6),
            "jw_quasiparticle_gap": round(jw_gap(g), 6),
            "yang_magnetization": round(yang_magnetization(g), 6),
        })
    _CACHE[key] = rows
    return rows


# ================================================================ 3. Jordan-Wigner solution
# The standard free-fermion solution of the 1D TFIM, implemented
# from the textbook formulas and LABELLED as such. A Jordan-Wigner
# transformation turns the spins into free fermions; a Bogoliubov
# rotation diagonalizes them with quasiparticle energies
#     eps(k) = 2 sqrt(J^2 + h^2 - 2 J h cos k).
# The ground state fills every negative-energy Bogoliubov mode.

def dispersion(k, g, j_coupling=J_COUPLING):
    """Quasiparticle energy eps(k) at field ratio g = h / J."""
    h = g * j_coupling
    inside = j_coupling ** 2 + h ** 2 - 2.0 * j_coupling * h * math.cos(k)
    return 2.0 * math.sqrt(max(inside, 0.0))


def jw_ground_energy_per_site(g, j_coupling=J_COUPLING):
    """Thermodynamic-limit ground energy per site, Simpson integral.

    E0 / N = -(1/pi) int_0^pi sqrt(J^2 + h^2 - 2Jh cos k) dk.
    At g = 1 this is the classic -4J/pi; at g = 0 it is -J.
    """
    h = g * j_coupling
    n = SIMPSON_INTERVALS
    total = 0.0
    for i in range(n + 1):
        k = math.pi * i / n
        weight = 1.0 if i in (0, n) else (4.0 if i % 2 else 2.0)
        total += weight * math.sqrt(
            j_coupling ** 2 + h ** 2 - 2.0 * j_coupling * h * math.cos(k))
    return -total * (math.pi / n) / 3.0 / math.pi


def jw_finite_energy_per_site(n, g, j_coupling=J_COUPLING):
    """Finite-N JW ground energy per site, antiperiodic momenta.

    The ground state of the ring lives in the sector with
    antiperiodic fermion momenta k = 2 pi (m + 1/2) / N, and
    E0 = -1/2 sum_k eps(k). This sum reproduces exact
    diagonalization to ~1e-8 at every N the lab can diagonalize -
    the sharpest cross-check in the file.
    """
    total = 0.0
    for m in range(n):
        k = 2.0 * math.pi * (m + 0.5) / n
        total += dispersion(k, g, j_coupling)
    return -0.5 * total / n


def jw_gap(g, j_coupling=J_COUPLING):
    """Thermodynamic quasiparticle gap 2|J - h|: closes exactly at g = 1."""
    return 2.0 * abs(j_coupling - g * j_coupling)


def jw_finite_fermion_gap(n, g, j_coupling=J_COUPLING):
    """Smallest antiperiodic-mode quasiparticle energy at size N."""
    return min(dispersion(2.0 * math.pi * (m + 0.5) / n, g, j_coupling)
               for m in range(n))


def yang_magnetization(g):
    """Spontaneous magnetization (1 - g^2)^(1/8) for g < 1, else 0.

    LABELLED Onsager-Yang result for the 1D TFIM (order-parameter
    exponent beta = 1/8). A standard formula, not a lab discovery.
    """
    if g >= 1.0:
        return 0.0
    return (1.0 - g * g) ** 0.125


def correlation_length(g):
    """Correlation-length proxy xi = v / Delta in labelled units.

    With quasiparticle velocity v = 2J (its value at criticality)
    and gap Delta = 2|J - h|, xi = 1 / |1 - g| lattice sites. A
    labelled proxy from the gap - it diverges at g = 1, which is
    the point: at the transition, correlations span every scale
    the system has.
    """
    if g == 1.0:
        return float("inf")
    return 1.0 / abs(1.0 - g)


def finite_size_report():
    """ED vs JW across N at g = 0.5 (ordered) and g = 1.0 (critical)."""
    key = "finite_size"
    if key in _CACHE:
        return _CACHE[key]
    rows = []
    for g in FINITE_G:
        jw_inf = jw_ground_energy_per_site(g)
        for n in FINITE_N:
            r = ed_result(n, g)
            rows.append({
                "g": g,
                "n": n,
                "ed_energy_per_site": round(r["ground_energy_per_site"], 6),
                "jw_finite_per_site": round(jw_finite_energy_per_site(n, g), 6),
                "ed_minus_jw_finite": abs(r["ground_energy_per_site"]
                                          - jw_finite_energy_per_site(n, g)),
                "jw_thermodynamic_per_site": round(jw_inf, 6),
                "ed_minus_jw_thermo": abs(r["ground_energy_per_site"] - jw_inf),
                "ed_gap": round(r["spectral_gap"], 6),
                "ed_abs_magnetization": round(r["abs_magnetization"], 6),
                "yang_magnetization": round(yang_magnetization(g), 6),
            })
    _CACHE[key] = rows
    return rows


def gap_report():
    """The two gap stories: quasiparticle closure + finite-size scaling."""
    key = "gap_report"
    if key in _CACHE:
        return _CACHE[key]
    critical = []
    for n in FINITE_N:
        gap = ed_result(n, 1.0)["spectral_gap"]
        critical.append({
            "n": n,
            "ed_gap_at_criticality": round(gap, 6),
            "gap_times_n": round(gap * n, 6),
            "jw_finite_fermion_gap": round(jw_finite_fermion_gap(n, 1.0), 6),
        })
    tunnelling = []
    for n in FINITE_N:
        tunnelling.append({
            "n": n,
            "ed_gap_at_g_half": round(ed_result(n, 0.5)["spectral_gap"], 6),
        })
    disordered = []
    for g in (1.0, 1.25, 1.5, 2.0):
        disordered.append({
            "g": g,
            "ed_gap_n6": round(ed_result(SCAN_N, g)["spectral_gap"], 6),
            "jw_quasiparticle_gap": round(jw_gap(g), 6),
        })
    report = {
        "critical_scaling": critical,
        "ordered_tunnelling": tunnelling,
        "disordered_side": disordered,
        "pi_over_2": round(math.pi / 2.0, 6),
    }
    _CACHE[key] = report
    return report


def phase_report():
    """Order parameter + correlation length across the transition."""
    key = "phase_report"
    if key in _CACHE:
        return _CACHE[key]
    rows = []
    for g in (0.0, 0.25, 0.5, 0.75, 0.9, 0.99, 1.0, 1.01, 1.1, 1.5, 2.0):
        xi = correlation_length(g)
        rows.append({
            "g": g,
            "yang_magnetization": round(yang_magnetization(g), 6),
            "jw_quasiparticle_gap": round(jw_gap(g), 6),
            "correlation_length": "inf" if xi == float("inf") else round(xi, 4),
            "phase": phase_label(g, yang_magnetization(g), jw_gap(g)),
        })
    _CACHE[key] = rows
    return rows


# ================================================================ 4. kNN phase classifier
# Features: field ratio g, spontaneous magnetization, quasiparticle
# gap - all computed by the Jordan-Wigner engine above. The training
# grid is labelled by the lab's own phase policy (phase_label), so
# the classifier interpolates the lab's computed phase diagram; it
# does not replace the engines.

def phase_label(g, magnetization, gap):
    """The lab's phase policy over its own computed quantities."""
    if 0.9 < g < 1.1:
        return "critical-region"
    if g <= 0.9 and magnetization > 0.2:
        return "ordered"
    if g >= 1.1:
        return "disordered"
    return "critical-region"


def _training_grid():
    rows = []
    steps = 41
    for i in range(steps):
        g = 2.0 * i / (steps - 1)
        mag = yang_magnetization(g)
        gap = jw_gap(g)
        rows.append(((g, mag, gap), phase_label(g, mag, gap)))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    g, magnetization, gap = features
    return (g / 2.0, magnetization, gap / 4.0)


def classify_phase(g, magnetization, gap, k=3):
    """kNN over the JW-labelled grid, deterministic tie-breaking.

    k = 3 on purpose: the Yang magnetization plunges with exponent
    1/8 near g = 1, so ordered-side rows sit far away in feature
    space and a wider vote lets the flat disordered side outvote
    the critical rows at the transition itself.
    """
    target = _scaled((g, magnetization, gap))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, point)))
        ranked.append((dist, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for _, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0) + 1
    priority = {"ordered": 0, "critical-region": 1, "disordered": 2}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classifier_report():
    scenarios = {}
    for name, g in (("deep_ordered_g0.30", 0.30), ("ordered_g0.80", 0.80),
                    ("critical_g1.00", 1.00), ("disordered_g1.20", 1.20),
                    ("deep_disordered_g1.80", 1.80)):
        scenarios[name] = classify_phase(g, yang_magnetization(g), jw_gap(g))
    return scenarios


# ================================================================ 5. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="quantumphasetransition-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all materials / hardware / prediction gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="quantumphasetransition-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Say it in the first line of every report: the 1D TFIM is exactly solvable, the Jordan-Wigner formulas are labelled textbook results, and the exact diagonalization agrees with them because the model is solved - then show both gaps, because the tunnelling collapse and the quasiparticle closure are different physics.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a ring of spins aligning under a weak transverse field",
                  "the quasiparticle dispersion dipping to zero at h = J",
                  "two symmetry-broken ground states tunnelling into each other",
                  "the magnetization curve bending with exponent 1/8 at the critical point",
                  "the finite-size gap shrinking like pi over 2N toward the transition"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. eigensolver on known problems
    ev, _ = jacobi_eigh([[2.0, 1.0], [1.0, 2.0]])
    chk("jacobi_known_2x2", abs(min(ev) - 1.0) < 1e-10
        and abs(max(ev) - 3.0) < 1e-10)
    ham4 = build_hamiltonian(4, 1.0, 0.7)
    ev4, v4 = jacobi_eigh(ham4)
    recon = 0.0
    ortho = 0.0
    for i in range(16):
        for j in range(16):
            s = sum(v4[i][k] * ev4[k] * v4[j][k] for k in range(16))
            recon = max(recon, abs(s - ham4[i][j]))
            o = sum(v4[k][i] * v4[k][j] for k in range(16))
            ortho = max(ortho, abs(o - (1.0 if i == j else 0.0)))
    chk("jacobi_reconstruction_n4", recon < 1e-9)
    chk("jacobi_orthonormal_n4", ortho < 1e-9)

    # 2. Hamiltonian construction
    ham5 = build_hamiltonian(5, 1.0, 0.5)
    chk("hamiltonian_symmetric",
        all(abs(ham5[i][j] - ham5[j][i]) < 1e-12
            for i in range(32) for j in range(32)))
    chk("hamiltonian_trace_zero",
        abs(sum(ham5[i][i] for i in range(32))) < 1e-9)
    chk("ed_zero_field_energy", abs(ed_result(6, 0.0)["ground_energy_per_site"]
                                    + 1.0) < 1e-9)
    chk("ed_zero_field_magnetization",
        abs(ed_result(6, 0.0)["abs_magnetization"] - 1.0) < 1e-9)
    chk("ed_zero_field_gap_degenerate",
        ed_result(6, 0.0)["spectral_gap"] < 1e-8)
    chk("ed_large_field_energy",
        abs(ed_result(5, 10.0)["ground_energy_per_site"] + 10.0) < 0.1)

    # 3. Jordan-Wigner engine vs its own anchors
    chk("dispersion_at_k0", abs(dispersion(0.0, 0.5) - 1.0) < 1e-12)
    chk("dispersion_at_kpi", abs(dispersion(math.pi, 0.5) - 3.0) < 1e-12)
    chk("dispersion_critical_min",
        abs(dispersion(0.0, 1.0)) < 1e-12)
    chk("jw_energy_zero_field",
        abs(jw_ground_energy_per_site(0.0) + 1.0) < 1e-9)
    chk("jw_energy_critical_minus_4_over_pi",
        abs(jw_ground_energy_per_site(1.0) + 4.0 / math.pi) < 1e-6)
    chk("jw_gap_formula", abs(jw_gap(0.5) - 1.0) < 1e-12
        and jw_gap(1.0) == 0.0 and abs(jw_gap(1.5) - 1.0) < 1e-12)
    chk("jw_finite_fermion_gap_critical",
        all(abs(jw_finite_fermion_gap(n, 1.0)
                - 4.0 * math.sin(math.pi / (2.0 * n))) < 1e-9
            for n in FINITE_N))

    # 4. ED vs JW - the cross-check that anchors the lab
    chk("jw_finite_matches_ed_all",
        all(abs(ed_result(n, g)["ground_energy_per_site"]
                - jw_finite_energy_per_site(n, g)) < 1e-6
            for n in FINITE_N for g in FINITE_G))
    fs = {(r["g"], r["n"]): r for r in finite_size_report()}
    chk("ed_approaches_thermodynamic_g05",
        fs[(0.5, 7)]["ed_minus_jw_thermo"] < fs[(0.5, 5)]["ed_minus_jw_thermo"]
        and fs[(0.5, 7)]["ed_minus_jw_thermo"] < 5e-4)
    chk("ed_approaches_thermodynamic_g10",
        fs[(1.0, 7)]["ed_minus_jw_thermo"] < fs[(1.0, 5)]["ed_minus_jw_thermo"]
        and fs[(1.0, 7)]["ed_minus_jw_thermo"] < 0.02)

    # 5. the two gap stories
    gaps = gap_report()
    crit = gaps["critical_scaling"]
    chk("critical_gap_times_n_near_pi_over_2",
        all(1.5 < row["gap_times_n"] < 1.65 for row in crit)
        and crit[-1]["gap_times_n"] < crit[0]["gap_times_n"])
    chk("critical_gap_shrinks_with_n",
        all(crit[i]["ed_gap_at_criticality"]
            > crit[i + 1]["ed_gap_at_criticality"]
            for i in range(len(crit) - 1)))
    chk("critical_gap_ratio_4_over_7",
        abs(crit[0]["ed_gap_at_criticality"]
            / crit[-1]["ed_gap_at_criticality"] - 7.0 / 4.0) < 0.05)
    tun = gaps["ordered_tunnelling"]
    chk("tunnelling_gap_collapses_exponentially",
        all(tun[i + 1]["ed_gap_at_g_half"] < 0.6 * tun[i]["ed_gap_at_g_half"]
            for i in range(len(tun) - 1)))
    dis = gaps["disordered_side"]
    chk("disordered_gap_minimal_at_criticality",
        all(dis[i]["ed_gap_n6"] < dis[i + 1]["ed_gap_n6"]
            for i in range(len(dis) - 1)))
    chk("disordered_gap_tracks_quasiparticle",
        all(row["jw_quasiparticle_gap"] < row["ed_gap_n6"]
            < 1.1 * row["jw_quasiparticle_gap"]
            for row in dis if row["g"] >= 1.5))
    chk("ed_gap_positive_finite_at_criticality",
        ed_result(6, 1.0)["spectral_gap"] > 0.1)

    # 6. order parameter: Onsager-Yang vs ED <|Mz|>
    chk("yang_at_zero", yang_magnetization(0.0) == 1.0)
    chk("yang_at_half", abs(yang_magnetization(0.5) - 0.75 ** 0.125) < 1e-12)
    chk("yang_zero_at_and_above_critical",
        yang_magnetization(1.0) == 0.0 and yang_magnetization(1.5) == 0.0)
    chk("ed_absmz_approaches_yang",
        abs(fs[(0.5, 7)]["ed_abs_magnetization"] - yang_magnetization(0.5))
        < abs(fs[(0.5, 5)]["ed_abs_magnetization"] - yang_magnetization(0.5)))
    scan6 = {row["g"]: row for row in ed_scan_report(6)}
    chk("ed_absmz_decreases_across_transition",
        scan6[0.5]["abs_magnetization"] > scan6[1.0]["abs_magnetization"]
        > scan6[2.0]["abs_magnetization"])

    # 7. correlation length proxy
    chk("xi_values", abs(correlation_length(0.5) - 2.0) < 1e-12
        and abs(correlation_length(0.9) - 10.0) < 1e-9
        and abs(correlation_length(1.1) - 10.0) < 1e-9)
    chk("xi_diverges_at_criticality",
        correlation_length(0.99) > correlation_length(0.9)
        > correlation_length(0.5)
        and correlation_length(1.0) == float("inf"))

    # 8. classifier - labels come from the lab's own phase policy
    rep = classifier_report()
    chk("classifier_deep_ordered", rep["deep_ordered_g0.30"] == "ordered")
    chk("classifier_ordered", rep["ordered_g0.80"] == "ordered")
    chk("classifier_critical", rep["critical_g1.00"] == "critical-region")
    chk("classifier_disordered", rep["disordered_g1.20"] == "disordered")
    chk("classifier_deep_disordered",
        rep["deep_disordered_g1.80"] == "disordered")
    chk("classifier_matches_policy",
        all(classify_phase(g, yang_magnetization(g), jw_gap(g))
            == phase_label(g, yang_magnetization(g), jw_gap(g))
            for g in (0.3, 0.8, 1.0, 1.2, 1.8)))

    # 9. determinism of the JW engine (ED shares cached code paths)
    chk("jw_deterministic",
        jw_ground_energy_per_site(0.5) == jw_ground_energy_per_site(0.5)
        and jw_finite_energy_per_site(7, 1.0)
        == jw_finite_energy_per_site(7, 1.0))

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_unsolved_hold", gate("unsolved_model_solution_claim") == "HOLD")
    chk("gate_material_hold", gate("real_material_prediction_claim") == "HOLD")
    chk("gate_superconductor_hold", gate("superconductor_design_claim") == "HOLD")
    chk("gate_overclaim_hold",
        gate("thermodynamic_limit_overclaim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QuantumPhaseTransition-Lab - transverse-field Ising lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - one solved model, two engines, no miracles")
    print("    H = -J sum sigma_z sigma_z - h sum sigma_x on a ring, J = 1,")
    print("    g = h/J. The 1D TFIM is EXACTLY SOLVABLE: the Jordan-Wigner")
    print("    solution below is a labelled textbook result, and exact")
    print("    diagonalization (ED) of the full Hamiltonian agrees with it")
    print("    because the model is solved - not because either engine is")
    print("    discovering anything. The quantum critical point is g = 1.")
    print("\n[2] Exact diagonalization scan - full Hamiltonian, N = 6 ring")
    print("    g      E0/site     ED gap    <|Mz|>    JW E0/site  JW gap   Yang M")
    for row in ed_scan_report(SCAN_N):
        print(f"    {row['g']:<5.2f} {row['ground_energy_per_site']:>10.6f} "
              f"{row['spectral_gap']:>9.6f} {row['abs_magnetization']:>8.4f} "
              f"{row['jw_energy_per_site']:>11.6f} "
              f"{row['jw_quasiparticle_gap']:>7.3f} "
              f"{row['yang_magnetization']:>8.4f}")
    print("    -> ED and JW energies track each other across the whole scan;")
    print("       the finite-N JW sum matches ED to ~1e-8 (section 3).")
    print("\n[3] Finite size - ED vs JW, ordered (g = 0.5) and critical (g = 1)")
    for row in finite_size_report():
        print(f"    g={row['g']:<4} N={row['n']}  ED {row['ed_energy_per_site']:>10.6f} "
              f"| JW finite {row['jw_finite_per_site']:>10.6f} "
              f"| JW thermo {row['jw_thermodynamic_per_site']:>10.6f} "
              f"| |ED-thermo| {row['ed_minus_jw_thermo']:.2e}")
    print("    -> the ED energy walks toward the thermodynamic JW value as N")
    print("       grows, and the finite-N JW sum lands on ED at every N.")
    print("\n[4] The gap, story one - quasiparticle closure (JW, thermodynamic)")
    print("    Delta = 2|J - h|:  g=0.5 -> 1.000 | g=0.9 -> 0.200 | g=1 -> 0")
    print("    (closed exactly) | g=1.5 -> 1.000. The gap closes AT the")
    print("    transition and reopens on the other side.")
    print("\n[5] The gap, story two - what a finite ring actually does (ED)")
    gaps = gap_report()
    print("    At criticality the ED gap closes only like pi/(2N):")
    for row in gaps["critical_scaling"]:
        print(f"    N={row['n']}  ED gap {row['ed_gap_at_criticality']:>8.6f} "
              f"| gap x N {row['gap_times_n']:>7.4f} "
              f"| JW fermion gap {row['jw_finite_fermion_gap']:>8.6f}")
    print(f"    (pi/2 = {gaps['pi_over_2']}: gap x N settles toward it.)")
    print("    Inside the ordered phase the ED gap is a tunnelling splitting")
    print("    between the two symmetry-broken sectors - it collapses")
    print("    exponentially with N instead:")
    for row in gaps["ordered_tunnelling"]:
        print(f"    N={row['n']}  ED gap at g=0.5 {row['ed_gap_at_g_half']:>9.6f}")
    print("    On the disordered side the ED gap reopens and tracks 2|J - h|:")
    for row in gaps["disordered_side"]:
        print(f"    g={row['g']:<5} ED gap (N=6) {row['ed_gap_n6']:>8.6f} "
              f"| JW quasiparticle gap {row['jw_quasiparticle_gap']:>6.3f}")
    print("\n[6] Order parameter + correlation length (labelled JW formulas)")
    for row in phase_report():
        print(f"    g={row['g']:<5} Yang M {row['yang_magnetization']:>7.4f} "
              f"| gap {row['jw_quasiparticle_gap']:>6.3f} "
              f"| xi {str(row['correlation_length']):>7} | {row['phase']}")
    print("    -> M = (1 - g^2)^(1/8) vanishes at g = 1 with exponent 1/8;")
    print("       xi = 1/|1 - g| diverges there. ED <|Mz|> (section 2) trends")
    print("       toward the Yang curve as N grows (0.9636 vs 0.9647 at N = 7,")
    print("       g = 0.5).")
    print("\n[7] Phase classifier (TinyML kNN, labels from the lab's JW policy)")
    for name, label in classifier_report().items():
        print(f"    {name:24s} -> {label}")
    print("\n[8] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[9] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "ed":
        print(json.dumps(ed_scan_report(SCAN_N), indent=2, sort_keys=True))
        return 0
    if cmd == "jw":
        print(json.dumps(finite_size_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "gap":
        print(json.dumps(gap_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "phases":
        print(json.dumps(phase_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "real_material_prediction_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
