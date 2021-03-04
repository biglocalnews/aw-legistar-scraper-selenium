import time
from datetime import datetime
import os
import shutil
from urllib.parse import urlparse
from copy import deepcopy

from numpy import nan, random
import pandas as pd
from bs4 import BeautifulSoup
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import StaleElementReferenceException, \
    NoSuchElementException


class LegistarScraper(object):

    def __init__(
            self,
            city_name,
            scrape_url,
            base_url=None,
            headless=True,
    ):
        """
        Initialize a scraper instance.
        Args:
            city_name: name of city ("San Jose")
            scrape_url: base URL to scrape
                ("https://sanjose.legistar.com/Calendar.aspx")
            headless: If True (default), operates browser headlessly. Set to
                False for debugging.
        """

        self.city_name = city_name
        self.city_name_lower = self.city_name.lower().replace(' ', '-')
        self.scrape_url = scrape_url
        self.base_url = '{uri.scheme}://{uri.netloc}/'.format(
            uri=urlparse(self.scrape_url)
        )

        options = Options()
        options.headless = headless
        self.driver = Firefox(options=options)
        self.driver.get(self.scrape_url)

    def _log(self, *args, **kwargs):
        print(*args, kwargs)


    def _click(self, item):
        self.driver.execute_script("arguments[0].scrollIntoView();", item)
        item.click()
        return

    def _get_page_links(self, driver):
        """
        Assemble a list of links to result pages.
        """
        pagelinks_xpath = "//td[@class='rgPagerCell NumericPages']/div[1]/a"
        pagelinks = driver.find_elements_by_xpath(pagelinks_xpath)
        pagelinks = pagelinks[:int(len(pagelinks) / 2)]
        return [l.text for l in pagelinks], pagelinks

    def _get_page_signature(self):
        """
        Capture a "signature" of the current displayed table so we can tell
        whether content has changed.
        """
        elm_id = 'ctl00_ContentPlaceHolder1_gridCalendar_ctl00__0'
        return self.driver.find_element_by_id(elm_id).text.strip()

    def _wait_for_table_load(self, page_signature, max_wait=None):
        """
        Periodically poll the table to check whether the content has changed.
        Args:
            page_signature: Previous page signature
            max_wait: Timeout period (s)

        Returns:
            status: either "loaded" or "timeout"
        """
        sig_match = True
        expired = False
        i = 0
        while sig_match and not expired:
            try:
                i += 1
                if i > 100:
                    return "timeout"
                time.sleep(0.1)
                new_sig = self._get_page_signature()
                sig_match = new_sig in [page_signature, '']
            except StaleElementReferenceException:
                sig_match = False
            except NoSuchElementException:
                sig_match = False
        return "loaded"

    def scrape_all_pages(self, **filter_args):
        """
        Iteratively click through pages of results and extract the table data.
        Args:
            **filter_args: Arguments to pass to the drop-down selection menus.

        Returns:
            page_data: a list of HTML source for each page of results.

        """

        dropdown_ids = [
            (
                'years',
                'ctl00_ContentPlaceHolder1_lstYears_Input',
                'ctl00_ContentPlaceHolder1_lstYears_DropDown'
            ),
            (
                'bodies',
                'ctl00_ContentPlaceHolder1_lstBodies_Input',
                'ctl00_ContentPlaceHolder1_lstBodies_DropDown'
            )
        ]

        for field, input_id, dropdown_id in dropdown_ids:
            dropdown_xpath = "//div[@id='{}']/div/ul/li".format(dropdown_id)

            # click on the dropdown menu
            self._click(self.driver.find_element_by_id(input_id))

            # wait for first list item to populate
            parent_xpath = "//div[@id='{}']..".format(dropdown_id)
            waiting = True
            while waiting:
                time.sleep(0.1)
                dropdown_text = self.driver. \
                    find_element_by_xpath(dropdown_xpath).text
                waiting = dropdown_text == ''

            # select filter term            
            if field in filter_args.keys():
                # if a particular filter is specified, use that
                elms = self.driver.find_elements_by_xpath(dropdown_xpath)
                filter_options = [elm.text for elm in elms]
                try:
                    i = filter_options.index(filter_args[field])
                except ValueError:
                    self._log('scraper: unable to find item {} in list {}, '
                        'aborting:'.format(
                        filter_args[field], field), self.city_name)
                    return []
                filter_elm = elms[i]
            else:
                # if not, select first option in dropdown
                filter_elm = self.driver.find_element_by_xpath(dropdown_xpath)
            self._click(filter_elm)

            # click search button
            search_button_id = 'ctl00_ContentPlaceHolder1_btnSearch'
            search_button = self.driver.find_element_by_id(search_button_id)
            self._click(search_button)

        # click through pages and save html
        c = 1
        page_data = []
        while True:
            # scrape the page data
            self._log('scraper: scraping page {}'.format(c))
            page_data.append(self.driver.page_source)

            # increase page count
            c += 1

            # get page links, if any            
            try:
                pages, pagelinks = self._get_page_links(self.driver)
                page_signature = self._get_page_signature()
            except NoSuchElementException:
                self._log('scraper: could not find data table on page, '
                         'aborting:'
                    ' {}'.format(self.city_name))
                return []

            # click  through pages
            if pages:
                try:
                    # click on the integer we want
                    i = pages.index(str(c))
                    link = pagelinks[i]
                except:
                    # if it's not there and the list ends with '...',
                    # then click on '...'
                    if pages[-1] == '...':
                        link = pagelinks[-1]
                    # if it's not there and the list starts with '...',
                    # then we are done.
                    else:
                        break
                self._click(link)
            else:
                break

            #  wait for page to load
            timeout = self._wait_for_table_load(page_signature)
            if timeout == "timeout":
                break
            else:
                pass

        return page_data

    def extract_table_data(
            self,
            page_source,
            table_id='#ctl00_ContentPlaceHolder1_gridCalendar_ctl00'
    ):
        """

        Args:
            page_source: the HTML source of the webpage
            table_id: the id of the HTML table to poll
        Returns:
            table_data: a pandas dataframe corresponding to the HTML table
        """
        # find table in page
        soup = BeautifulSoup(page_source, features='lxml')
        table = soup.select(table_id)[0]

        # extract column headers
        header_data = [
            ''.join(cell.stripped_strings) for cell in table.find_all('th')
        ]
        header_data = [h for h in header_data if h != 'Data pager']
        num_cols = len(header_data)
        # num_cols = int(table.td.get('colspan'))

        # extract text and URL data from table
        text_data, url_data = [], []
        for row in table.find_all('tr'):
            row_text, row_url = [], []
            for td in row.find_all('td'):
                row_text.append(''.join(td.stripped_strings))
                if td.find('a') and (td.a.get('href') is not None):
                    row_url.append(self.base_url + td.a.get('href'))
                else:
                    row_url.append(nan)
                if len(row_text) == num_cols and len(row_url) == num_cols:
                    text_data.append(row_text)
                    url_data.append(row_url)

        # turn into dataframe
        num_cols = table.td.get('colspan')
        text_df = pd.DataFrame(text_data, columns=header_data)
        url_df = pd.DataFrame(url_data, columns=header_data)
        table_data = pd.merge(
            text_df,
            url_df,
            left_index=True,
            right_index=True,
            suffixes=(' Text', ' URL'))

        return table_data

    def extract_doc_list(self, page_data):
        """
        Convert a scraped (Legistar-formatted) table into a dataframe of
        documents.
        Args:
            page_data: a (Legistar-formatted) dataframe

        Returns:
            doc_list: a dataframe of unique documents
        """

        doc_list = []
        for i, row in page_data.iterrows():
            meeting_data = {
                'city': self.city_name,
                'date': pd.to_datetime(row['Meeting Date Text']),
                'committee': row['Name Text'],
                'doc_format': 'pdf',
            }
            url_col_pairs = [
                ('Agenda', 'Agenda URL'),
                ('Minutes', 'Minutes URL'),
                ('Minutes', 'Official Minutes URL')
            ]
            for doc_type, url_col in url_col_pairs:
                try:
                    url = row[url_col]
                    if isinstance(url, str):
                        row_data = deepcopy(meeting_data)
                        row_data['url'] = url
                        row_data['doc_type'] = doc_type
                        doc_list.append(row_data)
                except:
                    pass

        return pd.DataFrame(doc_list)

    def extract_all_table_data(self, save_dir='', **filter_args):
        """
        Extract all the documents that match given filters, and save to csv.
        Args:
            save_dir: if given, the directory in which to save the output.
            **filter_args: Arguments for refining the document search.

        Returns:
            doc_list: a formatted dataframe of documents
        """

        # get htmls of pages
        page_htmls = self.scrape_all_pages(**filter_args)
        if not page_htmls:
            return [], ''
        self._log('scraper: scraped {} pages'.format(len(page_htmls)))

        # convert to dataframes and concatenate
        page_dfs = [
            self.extract_table_data(page) for page in page_htmls
        ]
        page_data = pd.concat(page_dfs)
        self._log('scraper: recovered {} meetings'.format(len(page_data)))

        # extract document list
        doc_list = self.extract_doc_list(page_data)
        self._log('scraper: recovered {} documents'.format(len(doc_list)))

        if save_dir:
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
            fname = '{}.csv'.format(self.city_name_lower)
            doc_list_path = os.path.join(save_dir, fname)
            doc_list.to_csv(doc_list_path)
        else:
            doc_list_path = ''

        return doc_list, doc_list_path


def scrape_city(save_dir, scraper_args, filter_args):
    """
    Launch a scraper instance, scrape the city, quit.
    Args:
        save_dir: Path to directory in which to save output.
        scraper_args: Arguments to pass to LegistarScraper.
        filter_args: Arguments to pass to extract_all_table_data.

    Returns:
        doc_list_path

    """
    # launch scraper
    scraper = LegistarScraper(**scraper_args)

    # run scraping tool
    doc_list_path = scraper.extract_all_table_data(save_dir, **filter_args)

    # quit browser
    scraper.driver.quit()

    return doc_list_path


if __name__ == '__main__':
    import argparse
    from string import ascii_letters

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--output_dir",
        default='../data',
        help="Directory where scraping data live."
    )
    parser.add_argument(
        "-i", "--input",
        default='cities.csv',
        help="Path to CSV containing city endpoints."
    )
    parser.add_argument(
        "-y", "--year",
        default=str(datetime.utcnow().year),
        help="Filter by year (optional)."
    )
    parser.add_argument(
        "-b", "--bodies",
        help="Filter by body (optional)."
    )
    args = parser.parse_args()
    save_dir = os.path.abspath(args.output_dir)

    # add query filters
    filters = {}
    if args.year:
        filters['years'] = args.year
    if args.bodies:
        filters['bodies'] = args.bodies

    # parse list of cities
    city_csv_columns = ['city_name', 'scrape_url']
    city_df = pd.read_csv(args.input, header=None, names=city_csv_columns)

    # scrape each city in turn
    for _, city_args in city_df.iterrows():
        city_args = dict(city_args)
        print('Scraping city...', city_args)
        try:
            doc_list_path = scrape_city(save_dir, city_args, filters)
        except Exception as e:
            # send notification that scraping failed
            error_message = [
                'Error: Scraper failed on city. Did not scrape.',
                'City: {}'.format(city_args['city_name']),
                'URL: {}'.format(city_args['scrape_url']),
            ]

            # log error
            log_args = {
                'error_message': str(e),
            }
            log_args.update(city_args)
            print('Error: could not scrape city', log_args)
            continue

