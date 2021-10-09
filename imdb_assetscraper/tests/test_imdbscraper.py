from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from imdb_assetscraper import project_dir


@pytest.fixture
def scraper():
    from imdb_assetscraper.imdb_assetscraper import IMDBAssetScraper
    return IMDBAssetScraper(Path(""))


@pytest.fixture(scope='session')
def html_test():
    with Path(project_dir, 'imdb_assetscraper', 'tests', 'test_data.html').open(encoding='utf-8') as f:
        html_content = f.read()
    return html_content


@pytest.fixture(scope='session')
def soup(html_test):
    soup = BeautifulSoup(html_test, 'html.parser')
    return soup


class TestIMDBScraper:

    def test__parse_year_from_soup(self, scraper, soup):
        assert scraper._parse_year_from_soup(soup) == 2008

    def test__parse_runtime_from_soup(self, scraper, soup):
        assert scraper._parse_runtime_from_soup(soup) == 152

    def test__parse_genre_from_soup(self, scraper, soup):
        result = scraper._parse_genre_from_soup(soup)
        assert result == {'Action', 'Drama', 'Crime'}

    def test__parse_rating_from_soup(self, scraper, soup):
        assert scraper._parse_rating_from_soup(soup) == {'rating_imdb': 9.0, 'rating_imdb_count': 2400000}

    def test__parse_fsk_from_soup(self, scraper):
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

    def test__storyline_from_soup(self, scraper, soup):
        assert scraper._parse_storyline_from_soup(soup).startswith('Set within a year after the events')

    def test__parse_credits_from_soup(self, scraper):
        website = """
                <table class="cast_list">
  <tr><td colspan="4" class="castlist_label"></td></tr>
      <tr class="odd">
          <td class="primary_photo">
<a href="/name/nm0185819/?ref_=ttfc_fc_cl_i1"
><img height="44" width="32" alt="Daniel Craig" title="Daniel Craig" src="https://m.media-amazon.com/images/G/01/imdb/images/nopicture/32x44/name-2138558783._CB470041625_.png" class="loadlate hidden " loadlate="https://m.media-amazon.com/images/M/MV5BMjEzMjk4NDU4MF5BMl5BanBnXkFtZTcwMDMyNjQzMg@@._V1_UX32_CR0,0,32,44_AL_.jpg" /></a>          </td>
          <td>
<a href="/name/nm0185819/?ref_=ttfc_fc_cl_t1"
> Daniel Craig
</a>          </td>
          <td class="ellipsis">
              ...
          </td>
          <td class="character">
            <a href="/title/tt0830515/characters/nm0185819?ref_=ttfc_fc_cl_t1" >James Bond</a> 
                  
          </td>
      </tr>
      <tr class="even">
          <td class="primary_photo">
<a href="/name/nm1385871/?ref_=ttfc_fc_cl_i2"
><img height="44" width="32" alt="Olga Kurylenko" title="Olga Kurylenko" src="https://m.media-amazon.com/images/G/01/imdb/images/nopicture/32x44/name-2138558783._CB470041625_.png" class="loadlate hidden " loadlate="https://m.media-amazon.com/images/M/MV5BMTkyMzIwMjY1OF5BMl5BanBnXkFtZTcwNzA3MDkwOQ@@._V1_UX32_CR0,0,32,44_AL_.jpg" /></a>          </td>
          <td>
<a href="/name/nm1385871/?ref_=ttfc_fc_cl_t2"
> Olga Kurylenko
</a>          </td>
          <td class="ellipsis">
              ...
          </td>
          <td class="character">
            <a href="/title/tt0830515/characters/nm1385871?ref_=ttfc_fc_cl_t2" >Camille</a> 
                  
          </td>
      </tr>
        """
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_credits_from_soup(soup) == {'actor': [185819, 1385871]}

    def test__parse_credits_from_soup_without_credits(self, scraper):
        website = """<table>just an empty string ..."""
        soup = BeautifulSoup(website, 'html.parser')
        assert scraper._parse_credits_from_soup(soup) == {'actor': []}
