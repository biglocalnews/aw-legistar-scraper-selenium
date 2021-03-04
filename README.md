# aw-legistar-scraper-selenium
A Selenium-based Python scraper for pulling meeting agendas and minutes from
the Legistar platform. 
Takes in a minimally-formatted CSV of Legistar endpoints, and returns a
dataframe of document metadata (title, committee, document type, and so forth)
along with the URL to each document. Note that this script does not actually
download the documents it finds.

## Usage

The input to the script is a CSV formatted like `cities.csv` containing
endpoints to scrape. The script looks for this file at `./cities.csv` by
default. A different path may be passed via `-i`.

Scrape all cities in the file `/path/to/my/cities.csv`: 

    python legistar_scraper.py -i /path/to/my/cities.csv

The script writes its output to `../data` by default. A different directory may
be specified via `-o`. 

Scrape and write results to `/my/output/directory`: 

    python legistar_scraper.py -o /my/output/directory

The default behavior of the script is to return all historical documents on the 
platform, across all committees. In some cases, this can yield results going
back more than a decade. The Legistar platform allows some degree of filtering,
which are exposed here through two arguments, `-y` and `-b`. 

Find documents only from 2021:

    python legistar_scraper.py -y 2021

Find documents only from committees named "City Council" (note, not all city
councils go by the name "City Council"):

    python legistar_scraper.py -b "City Council"

The above arguments may be used in any combination.

## Requirements
`legistar_scraper.py` has been tested to work with:

    python 3.7.7
    numpy 1.18
    beautifulsoup4 4.9
    selenium 3.141
    pandas 1.0
    geckodriver 0.29.0

## Contributors

This script was written by Chris Stock for [Agenda Watch](http://agendawatch.org/),
a project of [Big Local News](https://biglocalnews.org/#/) at Stanford.