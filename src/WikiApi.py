from typing import List, Optional
import wikipediaapi
import functools
import requests
import logging
from models import ComarcaPage
from requests.exceptions import HTTPError, ConnectionError, Timeout, RequestException

def return_none(): return None
def return_empty_list(): return []

def catch_http_errors(default_return=lambda: None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except (HTTPError, ConnectionError, Timeout, RequestException) as http_exc:
                logging.error(f"HTTP exception in {func.__name__}: {http_exc}")
                return default_return()
        return wrapper
    return decorator

class WikipediaAPIHandler:
    def __init__(self, language: str = 'ca'):
        self.wiki = wikipediaapi.Wikipedia("Anki Catalunya (https://github.com/CaiClone)",language)

    def get_comarques(self) -> List[ComarcaPage]:
        comarques = self.wiki.page("Category:Comarques de Catalunya")
        comarques_pages = comarques.categorymembers
        page_categories = [page for page in comarques_pages.values() if
                           page.ns == wikipediaapi.Namespace.CATEGORY and self.is_comarca(page)]
        return [ComarcaPage(page.title.split(":")[-1]) for page in page_categories]

    def is_comarca(self, page) -> bool:
        if "de catalunya" in page.title.lower():
            return False
        for category in page.categories.values():
            if "categoria:comarques de catalunya" == category.title.lower():
                return True
        return False

class WikimediaAPIHandler:
    def __init__(self):
        self.commons_api_url = "https://commons.wikimedia.org/w/api.php"
        self.wikipedia_api_url = "https://ca.wikipedia.org/w/api.php"

    @catch_http_errors(default_return=return_none)
    def get_image_info(self, image_title: str) -> Optional[str]:
        params = {
            "action": "query",
            "prop": "imageinfo",
            "format": "json",
            "iiprop": "url",
            "titles": image_title.replace("Fitxer:", "File:"),
        }
        response = requests.get(self.commons_api_url, params=params).json()
        print(response.text)
        print("Do I really need the iter")
        page_id = next(iter(response["query"]["pages"]))
        if 'imageinfo' in response["query"]["pages"][page_id]:
            return response["query"]["pages"][page_id]["imageinfo"][0]["url"]
        return None

    @catch_http_errors(default_return=return_empty_list)
    def get_image_titles(self, page_title: str) -> List[str]:
        """
        Fetches titles of images from a specific Wikipedia page.
        
        Args:
        - page_title (str): The title of the Wikipedia page.
        
        Returns:
        - List[str]: A list of image titles from the page.
        """
        params = {
            "action": "query",
            "prop": "images",
            "format": "json",
            "titles": page_title
        }
        response = requests.get(self.wikipedia_api_url, params=params).json()
        page_id = next(iter(response["query"]["pages"]))
        if 'images' in response["query"]["pages"][page_id]:
            images = response["query"]["pages"][page_id]["images"]
            return [image["title"] for image in images]
        else:
            logging.warning(f"No images found for {page_title}")
            return []

    @catch_http_errors(default_return=return_empty_list)
    def get_images_for_comarca(self, comarca: ComarcaPage) -> None:
        """
        Fetches and updates a ComarcaPage instance with URLs for map and coat of arms images.
        
        Args:
        - comarca (ComarcaPage): The ComarcaPage instance to update with image information.
        """
        image_titles = self.get_image_titles(comarca.comarca)
        for title in image_titles:
            if "Mapa" in title: # not correct check test .ipynb
                comarca.map_url = self.get_image_info(title)
            elif "Escut" in title or "Coat of arms" in title:
                comarca.escut_url = self.get_image_info(title)
    # Also add the captial
    # and log if no escut