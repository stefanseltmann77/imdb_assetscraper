from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from imdb_assetscraper import project_dir
from imdb_assetscraper.imdb_assetscraper import IMDBAssetScraper


@pytest.fixture
def scraper() -> IMDBAssetScraper:
    return IMDBAssetScraper(Path(""))


@pytest.fixture(scope='session')
def html_test() -> str:
    with Path(project_dir, 'tests', 'resources', 'test_data_20230304.html').open(encoding='utf-8') as f:
        html_content = f.read()
    return html_content


@pytest.fixture(scope='session')
def soup(html_test: str) -> BeautifulSoup:
    soup = BeautifulSoup(html_test, 'html.parser')
    return soup


class TestIMDBScraper:

    def test__parse_year_from_soup(self, scraper: IMDBAssetScraper, soup: BeautifulSoup) -> None:
        assert scraper._parse_year_from_soup(soup) == 2008

    def test__parse_year(self, scraper: IMDBAssetScraper):
        input_str = "Bloodywood - Raj Against the Machine (The Documentary) (Video 2020) - IMDb"
        assert scraper._parse_year(input_str) == 2020

    def test__parse_runtime_from_soup(self, scraper: IMDBAssetScraper, soup: BeautifulSoup) -> None:
        assert scraper._parse_runtime_from_soup(soup) == 152

    def test__parse_genre_from_soup(self, scraper: IMDBAssetScraper, soup: BeautifulSoup) -> None:
        result = scraper._parse_genre_from_soup(soup)
        assert result == {'Action', 'Drama', 'Crime'}

    def test__parse_rating_from_soup(self, scraper: IMDBAssetScraper, soup: BeautifulSoup) -> None:
        assert scraper._parse_rating_from_soup(soup) == {'rating_imdb': 9.0, 'rating_imdb_count': 2700000}

    def test__parse_fsk_from_soup(self, scraper: IMDBAssetScraper) -> None:
        website = """<li class="ipl-inline-list__item"> <a href="/search/title?certificates=DE:16">Germany:16</a> 
                     (bw) </li>"""
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_fsk_from_soup(soup) == 16
        website = """<li class="ipl-inline-list__item">
                                    <a href="/search/title?certificates=DE:16">Germany:16</a>
                                </li>"""
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_fsk_from_soup(soup) == 16
        website = """<li class="ipl-inline-list__item">
                                    <a href="/search/title?certificates=DE:12">Germany:12</a>
                                </li>"""
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_fsk_from_soup(soup) == 12

    def test__storyline_from_soup(self, scraper: IMDBAssetScraper, soup: BeautifulSoup) -> None:
        assert scraper._parse_storyline_from_soup(soup).startswith('When the menace known as the Joker')

    def test__parse_credits_from_soup(self, soup: BeautifulSoup, scraper: IMDBAssetScraper) -> None:
        assert scraper._parse_credits_from_soup(soup)['actor'][:2] == [288, 5132]

    def test__parse_credits_from_soup_without_credits(self, scraper: IMDBAssetScraper) -> None:
        website = """<table>just an empty string ..."""
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_credits_from_soup(soup) == {'actor': []}
