import numpy as np
import pytest

from gocator_inspector import BAD, DOUBT, GOOD, Inspector, PreprocessConfig, list_images, sort_files
from gocator_inspector.__main__ import main as cli_main

from synthetic import make_dataset


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    return make_dataset(tmp_path_factory.mktemp("gocator"), seed=1)


@pytest.fixture(scope="module")
def trained(data):
    insp = Inspector(PreprocessConfig(invalid_zero=True))
    rep = insp.fit(list_images(data["buenas"]), list_images(data["malas"]))
    return insp, rep


def test_training_report(trained):
    insp, rep = trained
    assert rep.classifier and rep.n_good == 30 and rep.n_bad == 12
    conf = rep.confusion(insp.thresholds)
    assert conf is not None


def test_separates_bad_images(trained, data):
    insp, _ = trained
    df = insp.predict(list_images(data["inspeccionar"]))
    truth = data["truth"]
    df["es_mala"] = df["archivo"].map(truth)
    flagged = df["decision"].isin([BAD, DOUBT])
    recall = (flagged & df["es_mala"]).sum() / df["es_mala"].sum()
    false_bad = ((df["decision"] == BAD) & ~df["es_mala"]).sum()
    print(df[["archivo", "prob_mala", "anomalia", "decision", "es_mala"]].to_string())
    assert recall >= 0.9
    assert false_bad <= 2


def test_anomaly_only_mode(data):
    insp = Inspector(PreprocessConfig(invalid_zero=True))
    rep = insp.fit(list_images(data["buenas"]))
    assert not rep.classifier
    df = insp.predict(list_images(data["inspeccionar"]))
    df["es_mala"] = df["archivo"].map(data["truth"])
    assert df.loc[df["es_mala"], "anomalia"].median() > df.loc[~df["es_mala"], "anomalia"].median()


def test_save_load_and_sort(trained, data, tmp_path):
    insp, _ = trained
    insp.save(tmp_path / "m.joblib")
    insp2 = Inspector.load(tmp_path / "m.joblib")
    paths = list_images(data["inspeccionar"])[:5]
    a, b = insp.predict(paths), insp2.predict(paths)
    assert np.allclose(a["anomalia"], b["anomalia"])
    out = sort_files(a, tmp_path / "out")
    n = sum(len(list((tmp_path / "out" / d).iterdir())) for d in ("malas", "dudosas", "buenas"))
    assert n == 5 and list((tmp_path / "out").glob("informe_*.csv"))
    assert set(out["decision"]) <= {GOOD, BAD, DOUBT}


def test_cli(data, tmp_path):
    model = tmp_path / "m.joblib"
    assert cli_main(["entrenar", "--buenas", str(data["buenas"]), "--malas", str(data["malas"]),
                     "--modelo", str(model), "--cero-invalido"]) == 0
    assert cli_main(["separar", "--modelo", str(model), "--entrada", str(data["inspeccionar"]),
                     "--salida", str(tmp_path / "res")]) == 0
    assert any((tmp_path / "res" / "malas").iterdir())
