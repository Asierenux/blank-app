from supermercados.base import StoreError, normalize_unit, parse_unit_price_text, to_float
from supermercados.compare import basket_summary, search_all, sort_products
from supermercados.demo import demo_search
from supermercados.stores import Carrefour, Consum, Dia, Mercadona
from supermercados.base import Product


def test_to_float():
    assert to_float("1,25 €") == 1.25
    assert to_float("1.25") == 1.25
    assert to_float("1.234,50") == 1234.5
    assert to_float(2) == 2.0
    assert to_float(None) is None
    assert to_float("n/d") is None


def test_normalize_unit():
    assert normalize_unit("L", 1.0) == (1.0, "l")
    assert normalize_unit("kg", 3.2) == (3.2, "kg")
    assert normalize_unit("LITRE", 0.9) == (0.9, "l")
    assert normalize_unit("1 Litro", 0.9) == (0.9, "l")
    assert normalize_unit("100 g", 0.5) == (5.0, "kg")
    assert normalize_unit("docena", 2.4) == (0.2, "ud")
    assert normalize_unit("raro", 1.0) == (1.0, None)


def test_parse_unit_price_text():
    assert parse_unit_price_text("1,05 €/l") == (1.05, "l")
    assert parse_unit_price_text("(3,20 €/Kg)") == (3.2, "kg")
    assert parse_unit_price_text(None) == (None, None)


def test_mercadona_parse():
    hit = {
        "display_name": "Leche entera Hacendado",
        "packaging": "Brick",
        "thumbnail": "https://img/1.jpg",
        "share_url": "https://tienda.mercadona.es/product/1",
        "price_instructions": {"unit_price": "0.97", "reference_price": "0.970", "reference_format": "L"},
    }
    p = Mercadona().parse_hit(hit)
    assert p.price == 0.97 and p.unit == "l" and p.unit_price == 0.97
    assert p.name == "Leche entera Hacendado (Brick)"


def test_dia_parse():
    item = {
        "display_name": "Leche entera Dia",
        "url": "/leche/p/123",
        "image": "/product_images/123.jpg",
        "prices": {"price": 0.92, "price_per_unit": 0.92, "measure_unit": "LITRE"},
    }
    p = Dia().parse_item(item)
    assert p.price == 0.92 and p.unit == "l"
    assert p.url == "https://www.dia.es/leche/p/123"


def test_consum_parse_prefers_offer():
    item = {
        "productData": {"name": "Leche entera", "brand": {"name": "Consum"}, "url": "https://x"},
        "priceData": {
            "prices": [
                {"id": "PRICE", "value": {"centAmount": 1.0, "centUnitAmount": 1.0}},
                {"id": "OFFER_PRICE", "value": {"centAmount": 0.8, "centUnitAmount": 0.8}},
            ],
            "unitPriceUnitType": "1 Litro",
        },
    }
    p = Consum().parse_item(item)
    assert p.price == 0.8 and p.unit == "l" and p.brand == "Consum"


def test_carrefour_parse():
    doc = {"display_name": "Leche", "active_price": 1.05, "price_per_unit_text": "1,05 €/l", "url": "/p/1"}
    p = Carrefour().parse_doc(doc)
    assert p.price == 1.05 and p.unit_price == 1.05 and p.unit == "l"
    assert p.url == "https://www.carrefour.es/p/1"


def test_parsers_skip_items_without_price():
    assert Mercadona().parse_hit({"display_name": "x"}) is None
    assert Dia().parse_item({"display_name": "x"}) is None
    assert Consum().parse_item({}) is None
    assert Carrefour().parse_doc({}) is None


def _p(store, name, price, unit_price, unit="l"):
    return Product(store=store, name=name, price=price, unit_price=unit_price, unit=unit)


def test_sort_by_unit_price_vs_price():
    products = [
        _p("A", "leche pack 6", 5.4, 0.9),
        _p("B", "leche 1 L", 1.0, 1.0),
        _p("C", "leche sin unidad", 0.5, None, None),
    ]
    assert [p.store for p in sort_products(products, True)] == ["A", "B", "C"]
    assert [p.store for p in sort_products(products, False)] == ["C", "B", "A"]


def test_search_all_handles_errors_and_filters():
    def fake(store, query):
        if store == "Roto":
            raise StoreError("Roto: 403")
        return [_p(store, "Leche entera", 1.0, 1.0), _p(store, "Galletas", 2.0, 2.0, "kg")]

    [res] = search_all(["leche"], ["A", "Roto"], fake)
    assert res.errors == {"Roto": "Roto: 403"}
    assert [p.name for p in res.products] == ["Leche entera"]


def test_basket_summary_with_demo():
    queries = ["leche entera", "huevos", "producto inexistente"]
    stores = ["Mercadona", "Dia"]
    results = search_all(queries, stores, lambda s, q: demo_search(s, q))
    summary = basket_summary(results)
    rows = summary["rows"]
    assert list(rows["Artículo"]) == queries
    assert rows.iloc[2]["Producto"] == "No encontrado"
    assert set(summary["totals"]) == set(stores)
    assert summary["missing"] == {"Mercadona": 1, "Dia": 1}
    assert summary["mixed_total"] <= min(summary["totals"].values())
