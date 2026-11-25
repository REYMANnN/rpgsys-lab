"""Testes da fase 0: reprodutibilidade e controles."""
import copy

from jobs.roofline_smoke import DEFAULT_INPUTS, roofline
from lab.manifest import run_job, sha256_of


def test_same_inputs_same_seed_same_hash():
    a = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, 42)
    b = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, 42)
    assert a.outputs_sha256 == b.outputs_sha256
    assert a.inputs_sha256 == b.inputs_sha256


def test_negative_control_changed_input_changes_hash():
    altered = copy.deepcopy(DEFAULT_INPUTS)
    altered["mem_bw_tbs"] = 8.000001
    a = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, 42)
    b = run_job("roofline_smoke", roofline, altered, 42)
    assert a.inputs_sha256 != b.inputs_sha256
    assert a.outputs_sha256 != b.outputs_sha256


def test_negative_control_changed_seed_changes_hash():
    a = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, 42)
    b = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, 43)
    assert a.outputs_sha256 != b.outputs_sha256


def test_hash_is_canonical():
    assert sha256_of({"b": 1, "a": 2}) == sha256_of({"a": 2, "b": 1})


def test_roofline_physics_sanity():
    out = roofline(DEFAULT_INPUTS, 42)
    # Abaixo do ponto de cume, limitado por memória; acima, por cálculo.
    assert out["attainable_tflops"]["1"] == DEFAULT_INPUTS["mem_bw_tbs"] * 1
    assert out["attainable_tflops"]["512"] == DEFAULT_INPUTS["peak_tflops"]
    assert out["ridge_point"] == DEFAULT_INPUTS["peak_tflops"] / DEFAULT_INPUTS["mem_bw_tbs"]
