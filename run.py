import logging
import os
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import wikipediaapi
import genanki
import glob
from pathlib import Path
from tqdm import tqdm

from src.models import ComarcaData

WIKI_USERAGENT = "Anki Catalunya (https://github.com/CaiClone)"

def get_comarques_categories(wiki: wikipediaapi.Wikipedia) -> List[wikipediaapi.WikipediaPage]:
    """Retrieve comarques categories from Wikipedia."""
    comarques = wiki.page("Category:Comarques de Catalunya")
    comarques_pages = comarques.categorymembers
    return [page for page in comarques_pages.values() if page.ns == wikipediaapi.Namespace.CATEGORY and is_comarca(page)]

def is_comarca(page) -> bool:
    if "de catalunya" in page.title.lower():
        return False
    for category in page.categories.values():
        if "categoria:comarques de catalunya" == category.title.lower():
            return True
    return False

def get_image_titles(page_title: str) -> List[str]:
    """Get image titles from a Wikipedia page."""
    url = "https://ca.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "images",
        "format": "json",
        "titles": page_title
    }
    response = requests.get(url, params=params).json()
    page_id = next(iter(response["query"]["pages"]))
    images = response["query"]["pages"][page_id]["images"]
    return [image["title"] for image in images if image["title"].endswith('.svg')]


def get_image_info(image_title: str) -> Optional[str]:
    """Get image URL from Wikimedia Commons."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "imageinfo",
        "format": "json",
        "iiprop": "url",
        "titles": image_title.replace("Fitxer:", "File:")
    }
    response = requests.get(url, params=params).json()
    page_id = next(iter(response["query"]["pages"]))
    if 'imageinfo' in response["query"]["pages"][page_id]:
        image_info = response["query"]["pages"][page_id]["imageinfo"][0]
        return image_info["url"]
    else:
        logging.warning(f"No image info found for {image_title}")
        return None

def download_svg(url: str, filename: str):
    """Download an SVG file."""
    try:
        # follow wikimedia user
        response = requests.get(url, headers={"User-Agent": WIKI_USERAGENT})
                                
        response.raise_for_status()
        with open(filename, 'wb') as file:
            file.write(response.content)
    except Exception as e:
        logging.error(f"Failed to download {url}: {e}")

def get_comarca_capital_from_html(page_url):
    """Extract the capital of a comarca from its Wikipedia page URL."""
    response = requests.get(page_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the table row (`tr`) with a `th` having "Capital" as string
    capital_row = soup.find('th', string='Capital').parent if soup.find('th', string='Capital') else None
    
    if capital_row:
        # Extract the text from the first link (`a`) tag within the capital row
        capital_link = capital_row.find('a')
        if capital_link:
            return capital_link.text  # The name of the capital
        else:
            return "Capital not found in the expected format"
    else:
        return "Capital row not found"

def get_comarca_data(comarca_name: str) -> Optional[ComarcaData]:
    images = get_image_titles(comarca_name)
    map_urls = [get_image_info(image) for image in images if image.endswith("a Catalunya.svg")]
    escut_urls = [get_image_info(image) for image in images if "Coat" in image]
    comarca_path = comarca_name.replace(" ", "_")
    data = ComarcaData(
        comarca = comarca_name,
        capital = get_comarca_capital_from_html(f"https://ca.wikipedia.org/wiki/{comarca_path}")
    )
    for urls, field in [(map_urls, "map"), (escut_urls, "escut")]:
        if len(urls) == 0:
            logging.warning(f"No {field} found for {comarca_name}")
            continue
        path = f"imgs/{comarca_path}_{field}.svg"
        download_svg(urls[0], path)
        setattr(data, f"{field}_url", path)
    return data

def validate_data(data: List[ComarcaData]) -> bool:
    for field, required in [
        ("capital", True),
        ("map_url", True),
        ("escut_url", False)
    ]:
        missing = [
            comarca.comarca for comarca in data if not getattr(comarca, field)
        ]
        if missing and required:
            logging.error(f"Missing {field} for comarques: {','.join(missing)}")
            return False
        elif missing:
            logging.warning(f"Missing {field} for comarques: {','.join(missing)}")
    return True

def load_templates(path: str = "style/templates"):
    template_files = glob.glob(f"{path}/*.html")
    templates = []
    for file in template_files:
        with open(file, 'r') as f:
            text = f.read()
            front, back = text.split("\n--\n")
            templates.append({
                "name": Path(file).stem,
                "qfmt": front,
                "afmt": back
            })
    return templates

def load_style(path: str = "style/style.css"):
    return open(path, "r").read()


def create_model() -> genanki.Model:
    templates, style = load_templates(), load_style()
    return genanki.Model(
        1529025036,
        'Comarques Catalanes Model',
        fields = [
            {'name': 'Capital'},
            {'name': 'Capital hint'},
            {'name': 'Capital info'},
            {'name': 'Comarca'},
            {'name': 'Comarca info'},
            {'name': 'Escut'}, 
            {'name': 'Escut similarity'},
            {'name': 'Map'}
        ],
        templates=templates,
        css=style)

def get_notes(data: List[ComarcaData], model) -> List[genanki.Note]:
    return [genanki.Note(
            model=model,
            fields= [
                comarca.capital,
                '', # capital hint
                '', # capital info
                comarca.comarca,
                '', # comarca info
                f'<img src="{Path(comarca.escut_url).name}">',
                '', # escut similarity
                f'<img src="{Path(comarca.map_url).name}">'
            ]
        ) for comarca in data]

def create_deck(notes: List[genanki.Note], imgs: List[str]) -> genanki.Package:
    deck = genanki.Deck(
        1859898804,
        'Comarques Catalanes')
    for note in notes:
        deck.add_note(note)
    pkg = genanki.Package(deck)
    pkg.media_files = imgs
    return pkg

def main():
    os.makedirs("imgs", exist_ok=True)
    wiki = wikipediaapi.Wikipedia(WIKI_USERAGENT,'ca')
    comarques = get_comarques_categories(wiki)
    progress = tqdm(comarques, desc="Processing comarques")
    data = []
    for comarca in progress:
        title = comarca.title.split(":")[-1]
        progress.set_postfix_str(title)
        data.append(get_comarca_data(title))
    valid = validate_data(data)
    if not valid:
        exit(-1)
    model = create_model()
    notes = get_notes(data, model)
    imgs = [getattr(comarca,field) for comarca in data for field in ComarcaData.MEDIA_FILES if getattr(comarca, field)]
    pkg = create_deck(notes, imgs)
    path = "comarques.apkg"
    pkg.write_to_file(path)
    print(f"Deck created at {path} with {len(notes)} notes")

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    main()
