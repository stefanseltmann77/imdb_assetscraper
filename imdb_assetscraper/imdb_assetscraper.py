import logging
import re
from dataclasses import dataclass
from logging import NullHandler
from pathlib import Path
from typing import Optional, Any
from urllib import request
from urllib.request import HTTPCookieProcessor

import bs4
from bs4 import BeautifulSoup


@dataclass
class IMDBAsset:
    imdb_movie_id: int
    title_orig: str
    year: int
    duration: Optional[int]
    fsk: int
    storyline: str
    genres: set[str]
    persons: dict[str, list[int]]
    awards: dict[str, Any]
    ratings: dict
    budget: Optional[int]
    synopsis: str


class IMDBAssetScraper:
    logger: logging.Logger
    URL_BASE: str = 'https://imdb.com/title/tt'
    dir_cache: Path

    def __init__(self, dir_cache: Path):
        """:param dir_cache: local directory where the scraped objects will be stored."""
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(NullHandler())
        self.dir_cache = dir_cache

    def process_imdb_movie_id(self, imdb_movie_id: int, use_cache: bool = False) -> IMDBAsset:
        """Get website for a given imdb_movie_id and return parsed asset

        :param imdb_movie_id: Id as an int according to the imdb website,
                              e.g. 76759 for https://www.imdb.com/title/tt0076759
        :param use_cache: if true, a already stored string will be used and no request to the website will be made.
                          This is useful if the parse is extended and
                          you don't want to reload for the web for every run
        :return: parsed asset data as a data class
        """
        content = self.get_webcontent_4_imdb_movie(imdb_movie_id, use_cache=use_cache)
        asset = self.parse_webcontent_4_imdb_movie(imdb_movie_id, content)
        return asset

    def get_webcontent_4_imdb_movie(self, imdb_movie_id: int, use_cache: bool = False) -> str:
        """Provide the website for a given imdb_movie_id as a string to be parsed

        :param imdb_movie_id: unique ID used by imdb
        :param use_cache: if true, a already stored string will be used and no request to the website will be made
        :return: raw string of the website
        """
        website_string: bytes = b""
        file_path: Path = Path(self.dir_cache, f"{imdb_movie_id}.imdb_movie")
        if use_cache:
            try:
                website_string = file_path.read_bytes()
                self.logger.info(f"Loading cached website for {imdb_movie_id=}.")
            except FileNotFoundError:
                self.logger.info(f"{imdb_movie_id=} not found in cache.")
        if not website_string or not use_cache:
            self.logger.info(f"Retrieving website for {imdb_movie_id=}.")
            url_movie: str = self.URL_BASE + str(imdb_movie_id).zfill(7) + "/"
            opener = request.build_opener(HTTPCookieProcessor())
            website_string = opener.open(url_movie).read()
            for sub_site in ('parentalguide', 'fullcredits', 'awards', 'business', 'companycredits', 'technical',
                             'keywords', 'plotsummary'):
                self.logger.debug(f"Start loading {sub_site=}.")
                website_sub = opener.open(f'{url_movie}{sub_site}')
                website_string += website_sub.read()
            file_path.write_bytes(website_string)
        return website_string.decode("utf-8")

    def parse_webcontent_4_imdb_movie(self, imdb_movie_id: int, website: str) -> IMDBAsset:
        self.logger.info(f"Parsing webcontent for {imdb_movie_id=}")
        soup = BeautifulSoup(website, 'html.parser')
        title_orig = soup.find('meta', {'property': 'og:title'})['content']
        persons = self._parse_credits_from_soup(soup.find('div', {'id': 'fullcredits_content'}))
        directors_raw = soup.find('h4', text=re.compile('Directed by')).find_next('tbody').find_all('a')
        for director_raw in directors_raw:
            persons.setdefault('director', []).append(re.findall('name/nm.*/', director_raw['href'])[0][7:-1])
        asset_obj = IMDBAsset(imdb_movie_id,
                              title_orig=title_orig.split('(')[0].strip(),
                              year=self._parse_year_from_soup(soup),
                              duration=self._parse_runtime_from_soup(soup),
                              fsk=self._parse_fsk_from_soup(soup),
                              storyline=self._parse_storyline_from_soup(soup),
                              genres=self._parse_genre_from_soup(soup),
                              persons=persons,
                              awards=self._parse_awards_from_soup(soup),
                              ratings=self._parse_rating_from_soup(soup),
                              budget=self._parse_budget_from_soup(soup),
                              synopsis=self._parse_synopsis_from_soup(soup)
                              )
        return asset_obj

    @staticmethod
    def _parse_rating_from_soup(soup: BeautifulSoup):
        try:
            rating_imdb_raw = soup.select('span[class^="AggregateRatingButton__RatingScore"]')[0].get_text()
            rating_imdb_count_raw = soup.select('div[class^="AggregateRatingButton__TotalRatingAmount"]')[0].get_text()
        except IndexError:
            try:
                rating_imdb_raw = soup.find('span', attrs={'itemprop': 'ratingValue'}).get_text()
                rating_imdb_count_raw = soup.find('span', attrs={'itemprop': 'ratingCount'}).get_text()
            except AttributeError:
                rating_imdb_raw = soup.find('div', attrs={
                    'data-testid': 'hero-rating-bar__aggregate-rating__score'}).span.get_text()
                rating_imdb_count_raw = soup.find('div', attrs={
                    'data-testid': 'hero-rating-bar__aggregate-rating__score'}).next_sibling.next_sibling.get_text()

        rating_imdb = float(rating_imdb_raw)

        if rating_imdb_count_raw.endswith('K'):
            rating_imdb_count = float(rating_imdb_count_raw[:-1]) * 1_000
        elif rating_imdb_count_raw.endswith('M'):
            rating_imdb_count = float(rating_imdb_count_raw[:-1]) * 1_000 * 1_000
        else:
            rating_imdb_count = int(rating_imdb_count_raw.replace(',', ''))

        return {'rating_imdb': rating_imdb,
                'rating_imdb_count': rating_imdb_count}

    @staticmethod
    def _parse_genre_from_soup(soup: BeautifulSoup) -> set[str]:
        genres_raw = soup.select('a[href^="/search/title?genres"]')
        try:
            genres = {element.span.get_text().strip() for element in genres_raw}
        except AttributeError:
            genres = {element.get_text().strip() for element in genres_raw}
        return genres

    @staticmethod
    def _parse_credits_from_soup(soup: BeautifulSoup) -> dict[str, list[int]]:
        soup_result = soup.find("table", attrs={'class': 'cast_list'})
        if soup_result:
            res: list[bs4.element.Tag] = soup_result.findChildren('a', {'href': re.compile('/name/nm+.')})
            actor_ids: list[int] = [int(chunk.attrs.get("href", "").split("/")[2][2:]) for chunk in res[::2]]
            persons = {'actor': actor_ids}
        else:
            persons = {'actor': []}
        return persons

    def _parse_storyline_from_soup(self, soup: BeautifulSoup) -> str:

        try:
            soup_result = soup.select('div[class^="Storyline__StorylineWrapper"]')[0]
            soup_result = soup_result.div.div.div.get_text()
            story_line = soup_result.replace("\n", "").replace('"', "").strip()
        except IndexError:
            try:
                story_line = soup.find('div', {'id': 'titleStoryLine'}).div.p.span.get_text().strip()
            except AttributeError:
                soup_result = soup.select('div[data-testid^="storyline-plot-summary"]')[0]
                story_line = soup_result.div.div.get_text().strip()
        return story_line

    def _parse_synopsis_from_soup(self, soup: BeautifulSoup) -> str:
        try:
            synopsis: str = soup.find('ul', {'id': 'plot-synopsis-content'}).get_text()
        except AttributeError:
            synopsis = ""  # fixme
        if not synopsis:
            self.logger.error("No synopsis found!")
        return synopsis.replace("\n", "").replace('"', "").strip()

    @staticmethod
    def _parse_budget_from_soup(soup: BeautifulSoup) -> Optional[int]:
        budget_raw = soup.find('li', {'data-testid': 'title-boxoffice-budget'})
        if budget_raw:
            budget_raw_content = budget_raw.div.get_text().strip()
            try:
                budget = budget_raw_content.replace('$', '').replace(',', '').replace('(estimated)', '').strip()
            except TypeError:
                budget = None
        else:
            budget = None
        return budget

    @staticmethod
    def _parse_year_from_soup(soup: BeautifulSoup) -> int:
        title_orig = soup.find('meta', {'property': 'og:title'})['content']
        return int(title_orig.split('(')[1].split(')')[0])

    @staticmethod
    def _parse_fsk_from_soup(soup: BeautifulSoup) -> int:
        """fsk is the German required age to access an asset"""
        soup_search_result = \
            soup.find_all('a', {'href': re.compile(r'/search/title\?certificates=(de|imdb_wg|DE|Germany):[0-9]')})
        if not soup_search_result:
            fsk = 99
        else:
            fsk = int(soup_search_result[0].text.split(':')[1])
        return fsk

    @staticmethod
    def _parse_runtime_from_soup(soup: BeautifulSoup) -> Optional[int]:

        search = list(soup.find('div', attrs={'id': 'technical_content'}).table.tr.children)[3].get_text()
        runtime = int(search.split('(')[1].split(' ')[0])
        return runtime

    @staticmethod
    def _parse_awards_from_soup(soup: BeautifulSoup) -> dict:
        search = soup.find_all('table', {'class': 'awards'})
        awards: dict = {}
        for award_table in search:
            cells = award_table.find_all('td')
            award_outcome_current = None
            award_category_current = None
            for cell in cells:
                cell_htmlclass = cell.get('class')[0]
                if cell_htmlclass == 'title_award_outcome':
                    award_outcome_current = cell.find('b').text
                    award_category_current = cell.find('span').text
                elif cell_htmlclass == 'award_description':
                    award_description = cell.text.split('\n')[1].strip()
                    awards.setdefault(award_category_current, []).append((award_description, award_outcome_current))
                else:
                    raise Exception
        return awards

    @staticmethod
    def get_chart_ids(listing: str):
        listing_map = {'URL_TOP250': "https://www.imdb.com/chart/top?ref_=nv_mv_250",
                       'URL_BOTTOM100': "https://www.imdb.com/chart/bottom",
                       'URL_TOP250_ENGL': "https://www.imdb.com/chart/top-english-movies"}
        listing_url = listing_map.get(listing)
        if not listing_url:
            raise Exception(f"Not supported listing. Choose from {listing_map.keys()}!")
        else:
            website = request.urlopen(listing_url).read()
            soup = BeautifulSoup(website, 'html.parser')
            return [int(finding['data-tconst'].strip('t')) for finding in soup.find_all('div', {'class': 'wlb_ribbon'})]
