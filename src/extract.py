"""
Passo 1 — Descompactação automatizada dos arquivos do FINBRA (Siconfi).

Percorre data/raw/<ano>/*.zip e extrai o finbra.csv de cada um para
data/interim/<ano>/finbra.csv, preservando o ano de origem (dado pela
pasta, não pelo conteúdo do arquivo).
"""

from pathlib import Path
import zipfile

RAW_DIR = Path("dados_compactos")  # pasta já existente no repo original do desafio
INTERIM_DIR = Path("data/interim")


def extract_all(raw_dir: Path = RAW_DIR, interim_dir: Path = INTERIM_DIR) -> list[Path]:
    """Extrai todos os .zip encontrados em raw_dir/<ano>/ para interim_dir/<ano>/.

    Retorna a lista de caminhos dos CSVs extraídos.
    """
    extracted_files = []

    # Cada subpasta de data/raw é um ano (ex.: data/raw/2020/*.zip)
    for year_folder in sorted(raw_dir.iterdir()):
        if not year_folder.is_dir():
            continue

        year = year_folder.name
        zips = list(year_folder.glob("*.zip"))

        if not zips:
            print(f"[aviso] Nenhum .zip encontrado em {year_folder}")
            continue

        target_dir = interim_dir / year
        target_dir.mkdir(parents=True, exist_ok=True)

        for zip_path in zips:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Assume que há um único CSV relevante dentro do zip
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    print(f"[aviso] Nenhum CSV dentro de {zip_path}")
                    continue

                for csv_name in csv_names:
                    zf.extract(csv_name, target_dir)
                    extracted_path = target_dir / csv_name
                    # Padroniza o nome para facilitar o transform.py
                    final_path = target_dir / "finbra.csv"
                    extracted_path.rename(final_path)
                    extracted_files.append(final_path)
                    print(f"[ok] {zip_path.name} -> {final_path}")

    return extracted_files


if __name__ == "__main__":
    files = extract_all()
    print(f"\nTotal de arquivos extraídos: {len(files)}")