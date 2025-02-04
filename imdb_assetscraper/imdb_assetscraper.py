import json
import logging
import re
from abc import abstractmethod, ABC
from dataclasses import dataclass
from logging import NullHandler
from pathlib import Path
from typing import Optional, Any, Union
from urllib import request
from urllib.request import HTTPCookieProcessor, Request

import bs4
from bs4 import BeautifulSoup, ResultSet


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
    ratings: dict[str, Any]
    budget: Optional[int]
    synopsis: str


class ParsingError(Exception):
    ...


class Parser(ABC):
    logger: logging.Logger

    def __init__(self, soup: BeautifulSoup):
        self.logger = logging.getLogger(__name__)
        self.soup = soup

    @abstractmethod
    def parse(self):
        pass


class ParserRatingJson(Parser):
    def parse(self) -> dict[str, Union[int, float, None]]:
        json_chunk = json.loads(self.soup.find('script', attrs={'type': 'application/ld+json'}).text)
        ratings_info = json_chunk['aggregateRating']
        rating_imdb = float(ratings_info['ratingValue'])
        rating_imdb_count = ratings_info['ratingCount']
        return {'rating_imdb': rating_imdb,
                'rating_imdb_count': rating_imdb_count}


class ParserFSK(Parser):
    def parse(self) -> int:
        res: ResultSet = self.soup.find_all('li', attrs={'data-testid': 'certificates-item'})
        for row in res:
            if "Germany" in row.text:
                fsk = int(row.find_next('a').text)
                break
        else:
            fsk = 99
        return fsk


class IMDBAssetScraper:
    logger: logging.Logger
    URL_BASE: str = 'https://imdb.com/title/tt'
    dir_cache: Path

    def __init__(self, dir_cache: Path, zip_exports: bool = False):
        """:param dir_cache: local directory where the scraped objects will be stored."""
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(NullHandler())
        self.dir_cache = dir_cache
        self.header: dict[str, str] = {'User-Agent': 'Mozilla/5.0'}

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
        :param use_cache: if true, an already stored string will be used and no request to the website will be made
        :return: raw string of the website, with all subsites appended
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
            self.logger.debug(f"URL {url_movie=}.")
            opener = request.build_opener(HTTPCookieProcessor())
            website_string = opener.open(Request(url_movie, headers=self.header)).read()
            for sub_site in ('parentalguide', 'fullcredits', 'awards', 'business', 'companycredits', 'technical',
                             'keywords', 'plotsummary'):
                self.logger.debug(f"Start loading {sub_site=}.")
                website_sub = opener.open(Request(f'{url_movie}{sub_site}/', headers=self.header))
                website_string += website_sub.read()
            file_path.write_bytes(website_string)
        return website_string.decode("utf-8")

    def _parse_titel_orig(self, soup):
        search = soup.find('meta', {'property': 'og:title'})
        if search:
            title_orig = search['content'].split('(')[0].strip()
            return title_orig
        else:
            raise Exception("No Original Titel found")

    def parse_webcontent_4_imdb_movie(self, imdb_movie_id: int, website: str) -> IMDBAsset:
        self.logger.info(f"Parsing webcontent for {imdb_movie_id=}")
        soup = BeautifulSoup(website, 'html.parser')
        asset_obj = IMDBAsset(imdb_movie_id,
                              title_orig=self._parse_titel_orig(soup),
                              year=self._parse_year_from_soup(soup),
                              duration=self._parse_runtime_from_soup(soup),
                              fsk=self._parse_fsk_from_soup(soup),
                              storyline=self._parse_storyline_from_soup(soup),
                              genres=self._parse_genre_from_soup(soup),
                              persons=self._parse_credits_from_soup(soup),
                              awards=self._parse_awards_from_soup(soup),
                              ratings=self._parse_rating_from_soup(soup),
                              budget=self._parse_budget_from_soup(soup),
                              synopsis=self._parse_synopsis_from_soup(soup)
                              )
        return asset_obj

    @staticmethod
    def _parse_rating_from_soup(soup: BeautifulSoup) -> dict[str, Union[int, float, None]]:

        try:
            return ParserRatingJson(soup).parse()
        except:
            pass

        try:
            res = soup.select('span[class^="AggregateRatingButton__RatingScore"]')[0]
            if res:
                rating_imdb_raw = res.get_text()
            else:
                rating_imdb_raw = 0
            rating_imdb_count_raw = soup.select('div[class^="AggregateRatingButton__TotalRatingAmount"]')[0].get_text()
        except IndexError:
            try:
                soup_result = soup.find('span', attrs={'itemprop': 'ratingValue'})
                if soup_result:
                    rating_imdb_raw = soup_result.get_text()
                else:
                    raise Exception()  # fixme
                soup_result = soup.find('span', attrs={'itemprop': 'ratingCount'})

                if soup_result:
                    rating_imdb_count_raw = soup_result.get_text()
                else:
                    raise Exception()  # fixme

            except AttributeError:
                res = soup.find('div', attrs={'data-testid': 'hero-rating-bar__aggregate-rating__score'})
                rating_imdb_raw = res.get_text() if res else None
                res = soup.find('div', attrs={'data-testid': 'hero-rating-bar__aggregate-rating__score'})
                rating_imdb_count_raw = res.next_sibling.next_sibling.get_text() if res else None

        if rating_imdb_raw and '/' in rating_imdb_raw:
            rating_imdb_raw = rating_imdb_raw.split('/')[0]

        rating_imdb = float(rating_imdb_raw) if rating_imdb_raw else None

        if rating_imdb_count_raw:
            if rating_imdb_count_raw.endswith('K'):
                rating_imdb_count = float(rating_imdb_count_raw[:-1]) * 1_000
            elif rating_imdb_count_raw.endswith('M'):
                rating_imdb_count = float(rating_imdb_count_raw[:-1]) * 1_000 * 1_000
            else:
                rating_imdb_count = int(rating_imdb_count_raw.replace(',', ''))
        else:
            rating_imdb_count = None
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
        result = soup.find('div', {'id': 'fullcredits_content'})
        if result:
            soup_result = result.find("table", attrs={'class': 'cast_list'})
            if soup_result:
                res: list[bs4.element.Tag] = soup_result.findChildren('a', {'href': re.compile('/name/nm+.')})
                actor_ids: list[int] = [int(chunk.attrs.get("href", "").split("/")[2][2:]) for chunk in res[::2]]
                persons = {'actor': actor_ids}
            else:
                persons = {'actor': []}
        else:
            persons = {'actor': []}

        if directors_tag := soup.find('h4', text=re.compile('Directed by')):
            directors_raw = directors_tag.find_next('tbody').find_all('a')
            for director_raw in directors_raw:
                persons.setdefault('director', []).append(re.findall('name/nm.*/', director_raw['href'])[0][7:-1])
        return persons

    def _parse_storyline_from_soup(self, soup: BeautifulSoup) -> str:

        try:
            soup_result = soup.find_all('div', attrs={'data-testid': 'sub-section-summaries'})
            story_line: str = soup_result[0].get_text(separator=" ")
        except IndexError:
            try:
                story_line = soup.find('div', {'id': 'titleStoryLine'}).div.p.span.get_text().strip()
            except AttributeError:
                try:
                    soup_result = soup.select('div[data-testid^="storyline-plot-summary"]')[0]
                    story_line = soup_result.div.div.get_text().strip()
                except IndexError:
                    soup_result = soup.select('ul[id="plot-summaries-content"]')[0]
                    summaries = [p_tag.text for p_tag in soup_result.select('p')]
                    story_line = '; '.join(summaries)
        return story_line

    def _parse_synopsis_from_soup(self, soup: BeautifulSoup) -> str:
        try:
            synopsis: str = soup.find('div', {'data-testid': 'sub-section-synopsis'}).get_text()
        except AttributeError:
            synopsis = ""  # fixme
        if not synopsis:
            self.logger.error("No synopsis found!")
        return synopsis.replace("\n", "").replace('"', "").strip()

    @staticmethod
    def _parse_budget_from_soup(soup: BeautifulSoup) -> int | None:
        budget_raw = soup.find('li', {'data-testid': 'title-boxoffice-budget'})
        if budget_raw:
            budget_raw_content = budget_raw.div.get_text().strip()
            try:
                budget: int | None = \
                    int(budget_raw_content.replace('$', '').replace('€', '').
                        replace(',', '').replace('(estimated)', '').strip())
            except TypeError:
                budget = None
        else:
            budget = None
        return budget

    def _parse_year_from_soup(self, soup: BeautifulSoup) -> int:
        result = soup.find('meta', {'property': 'og:title'})
        year = self._parse_year(result['content'])
        return year

    @staticmethod
    def _parse_year(raw_str: str) -> int:
        content_last_brackets = raw_str.split('(')[-1].split(')')[0]
        return int(content_last_brackets.replace("Video ", ""))

    @staticmethod
    def _parse_fsk_from_soup(soup: BeautifulSoup) -> int:
        """fsk is the German required age to access an asset"""

        return ParserFSK(soup).parse()

    @staticmethod
    def _parse_runtime_from_soup(soup: BeautifulSoup) -> Optional[int]:
        search_raw = soup.find_all('span', text=re.compile('\(\d*\smin\)'))
        search = [int(result.text.split(' min').pop(0)[1:]) for result in search_raw]
        return max(search)

    @staticmethod
    def _parse_awards_from_soup(soup: BeautifulSoup) -> dict[str, Any]:
        search = soup.find_all('table', {'class': 'awards'})
        awards: dict[str, Any] = {}
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
                    if award_category_current:  # from previous loop
                        awards.setdefault(award_category_current, []). \
                            append((award_description, award_outcome_current))
                else:
                    raise Exception
        return awards

    def get_chart_ids(self, listing: str) -> list[int]:
        listing_map = {'URL_TOP250': "https://www.imdb.com/chart/top?ref_=nv_mv_250",
                       'URL_BOTTOM100': "https://www.imdb.com/chart/bottom",
                       'URL_TOP250_ENGL': "https://www.imdb.com/chart/top-english-movies"}
        listing_url = listing_map.get(listing)
        if not listing_url:
            raise Exception(f"Not supported listing. Choose from {listing_map.keys()}!")
        else:
            website = request.urlopen(Request(listing_url, headers=self.header)).read()
            soup = BeautifulSoup(website, 'html.parser')
            return [int(finding['data-tconst'].strip('t')) for finding in soup.find_all('div', {'class': 'wlb_ribbon'})]
