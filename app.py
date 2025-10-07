import os
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for
import pandas as pd

app = Flask(__name__)

CSV_PATH = os.environ.get("MORADORES_CSV", os.path.join(os.path.dirname(__file__), "moradores.csv"))


class Resident:
    def __init__(self, full_name: str, phone_raw: str, block: str, apartment: str, email: str, note: str):
        self.full_name = full_name
        self.phone_raw = phone_raw
        self.block = block
        self.apartment = apartment
        self.email = email
        self.note = note

    @property
    def apartment_label(self) -> str:
        return f"{self.block}-{self.apartment}" if self.block and self.apartment else self.apartment or ""

    @property
    def whatsapp_link(self) -> str:
        # Attempt to normalize Brazilian phone: keep digits only, ensure country code 55
        digits = "".join(ch for ch in self.phone_raw if ch.isdigit())
        if digits.startswith("55"):
            num = digits
        else:
            num = "55" + digits
        return f"https://wa.me/{num}"


# Cache residents in memory for speed; reload on each process start
_residents_cache = None


def load_residents():
    global _residents_cache
    if _residents_cache is not None:
        return _residents_cache

    if not os.path.exists(CSV_PATH):
        _residents_cache = []
        return _residents_cache

    df = pd.read_csv(CSV_PATH)

    # Expected columns in Portuguese CSV
    expected = [
        "Nome do Morador",
        "Telefone com DDD",
        "Bloco",
        "Apartamento",
        "E-mail",
        "Mensagem Personalizada",
    ]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise RuntimeError(f"CSV missing required columns: {missing}")

    residents = []
    for _, row in df.iterrows():
        residents.append(
            Resident(
                full_name=str(row.get("Nome do Morador", "")).strip(),
                phone_raw=str(row.get("Telefone com DDD", "")).strip(),
                block=str(row.get("Bloco", "")).strip(),
                apartment=str(row.get("Apartamento", "")).strip(),
                email=str(row.get("E-mail", "")).strip(),
                note=str(row.get("Mensagem Personalizada", "")).strip(),
            )
        )

    _residents_cache = residents
    return residents


@app.get("/")
def index():
    # Search inputs
    query_name = request.args.get("nome", "").strip()
    query_apto = request.args.get("apto", "").strip()

    residents = load_residents()

    def matches(res: Resident) -> bool:
        ok = True
        if query_name:
            ok = ok and (query_name.lower() in res.full_name.lower())
        if query_apto:
            # match either exact apt number or block-apartment
            q = query_apto.lower()
            ok = ok and (
                q in (res.apartment or "").lower()
                or q in res.apartment_label.lower()
            )
        return ok

    filtered = [r for r in residents if matches(r)] if (query_name or query_apto) else []

    return render_template(
        "index.html",
        results=filtered,
        query_name=query_name,
        query_apto=query_apto,
    )


@app.get("/morador")
def resident_detail():
    # Identify by exact name + apartment to avoid duplicates
    name = request.args.get("nome", "").strip()
    apto = request.args.get("apto", "").strip()

    residents = load_residents()
    selected = None
    for r in residents:
        if r.full_name == name and (r.apartment == apto or r.apartment_label == apto or not apto):
            selected = r
            break

    if not selected:
        # fallback: try first matching by name only
        for r in residents:
            if r.full_name == name:
                selected = r
                break

    if not selected:
        return redirect(url_for("index"))

    return render_template("detail.html", resident=selected)


@app.post("/whatsapp/send")
def whatsapp_send():
    name = request.form.get("nome")
    apto = request.form.get("apto")
    message = request.form.get("mensagem", "").strip()

    residents = load_residents()
    selected = None
    for r in residents:
        if r.full_name == name and (r.apartment == apto or r.apartment_label == apto or not apto):
            selected = r
            break

    if not selected:
        return redirect(url_for("index"))

    base = selected.whatsapp_link
    text = urllib.parse.quote(message)
    return redirect(f"{base}?text={text}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
