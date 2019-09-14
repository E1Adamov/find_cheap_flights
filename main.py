import os
import sys
import traceback
import random
from smtplib import SMTP_SSL, SMTP_SSL_PORT
from datetime import datetime as dt
from typing import *
from email.message import EmailMessage

import requests
from bs4 import BeautifulSoup, element

import countries as target_countries
from filter_settings import filter_settings


class Price:
    def __init__(self, currency: str, amount: float):
        self.currency = currency
        self.amount = amount

    def __str__(self):
        return str(self.currency + str(self.amount))

    def __le__(self, other):
        return self.amount <= other

    def __ge__(self, other):
        return self.amount >= other


class Result:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __str__(self):
        output = ''
        for attr_name in self.__dict__:
            attr_value = getattr(self, attr_name)
            if isinstance(attr_value, dt):
                attr_value = attr_value.strftime('%d %b %Y')
            else:
                attr_value = str(attr_value)
            output += f'{attr_name}: {attr_value}\n'
        return output


class Country:
    def __init__(self, name: str, url: str, results: List[Result]):
        self.name = name
        self.url = url
        self.results = results

    def __iter__(self):
        return iter(self.results)

    def __next__(self):
        return next(self.results)


def get_all_parents(soup: BeautifulSoup, string: str) -> List[element.Tag]:
    all_elements = soup.find_all('span', string=string)
    parents = []
    for element in all_elements:
        parents.append(element.parent)
    return parents


def __get_all_dates(parents: List[element.Tag]) -> List[dt]:
    dates = []
    for i in parents:
        date_span = i.find('span', {'class': 'date'})
        date_text = date_span.text
        date_time = dt.strptime(date_text.split()[-1], "%d/%m/%y")
        dates.append(date_time)
    return dates


def get_all_there_dates(soup: BeautifulSoup) -> List[dt]:
    all_there_p = get_all_parents(soup, 'There')
    return __get_all_dates(all_there_p)


def get_all_back_dates(soup: BeautifulSoup) -> List[dt]:
    all_back_p = get_all_parents(soup, 'Back')
    return __get_all_dates(all_back_p)


def get_all_prices(soup: BeautifulSoup) -> List[Price]:
    all_prices_e = soup.find_all('span', {'class': 'doubleUnderline'})
    prices = []
    for p in all_prices_e:
        p_text = p.text
        currency = p_text[0]
        amount = float(p_text[1:])
        price = Price(currency, amount)
        prices.append(price)
    return prices


def get_all_var_names(module) -> List[str]:
    module = __import__(module)
    return [attr for attr in dir(module) if attr[:2] + attr[-2:] != '____']


def matches_filter(result: Result) -> bool:
    match_date_from = filter_settings['departure_from']
    match_date_to = filter_settings['departure_to']
    date_matches = match_date_from <= result.departure_date <= match_date_to
    price_matches = result.price <= filter_settings['price_to']
    return date_matches and price_matches


def get_normal_email_body(countries: List[Country]) -> str:
    body = ''
    for country in countries:
        body += country.name.upper() + '\n'
        body += country.url + '\n'
        for result in country:
            body += str(result) + '\n'
    return body


def get_exception_text(exception: Exception) -> str:
    exception_message = ''
    try:
        exception_message = exception.message
    except AttributeError:
        pass

    if not exception_message:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        exception_message = exc_value

    if not exception_message:
        exception_message = str(exception)

    return exception_message


def get_exception_email_body(exception: Exception, trace_back: str) -> str:
    exception_message = get_exception_text(exception)
    body = ''
    if exception_message:
        body += exception_message + '\n'
    if trace_back:
        for line in trace_back:
            body += line
    return body


def get_my_email() -> str:
    return os.getenv('EMAIL_ADDRESS')


def get_my_password() -> str:
    return os.getenv('EMAIL_PASSWORD')


def get_normal_message(countries: List[Country]) -> EmailMessage:
    msg = EmailMessage()
    EMAIL_ADDRESS = get_my_email()
    following_countries = ', '.join(c.name for c in countries)
    msg['Subject'] = f"FOUND CHEAP TICKETS TO {following_countries}!!!"
    msg['From'] = msg['To'] = EMAIL_ADDRESS
    body = get_normal_email_body(countries)
    msg.set_content(body)
    return msg


def get_exception_message(exception: Exception, trace_back: str) -> EmailMessage:
    msg = EmailMessage()
    EMAIL_ADDRESS = get_my_email()
    msg['Subject'] = f"!!!FAILED!!! FINDING CHEAP FLIGHTS"
    msg['From'] = msg['To'] = EMAIL_ADDRESS
    body = get_exception_email_body(exception, trace_back)
    msg.set_content(body)
    return msg


def get_email_message(countries: List[Country], exception: Exception, trace_back: str) -> EmailMessage:
    if exception:
        return get_exception_message(exception, trace_back)
    else:
        return get_normal_message(countries)


def send_email(message: EmailMessage):
    EMAIL_ADDRESS = get_my_email()
    EMAIL_PASSWORD = get_my_password()
    with SMTP_SSL('smtp.gmail.com', SMTP_SSL_PORT) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(message)


def validate_collections_length(data_containers: List[Dict]) -> int:
    lenghts = []
    for dict in data_containers:
        container = list(dict.values())[0]
        lenghts.append(len(container))

    msg = f"Soup parsing error: got different quantities in search results: {lenghts}"
    assert len(set(lenghts)) == 1, msg
    return lenghts[0]


def get_relevant_results(data_containers: List[Dict]) -> List[Result]:
    results_count = validate_collections_length(data_containers)

    relevant_results = []
    for idx in range(results_count):
        attrs = dict()
        for attr in data_containers:
            attr_name = list(attr.keys())[0]
            attr_value = list(attr.values())[0][idx]
            attrs[attr_name] = attr_value

        result = Result(**attrs)

        if matches_filter(result):
            relevant_results.append(result)
    return relevant_results


def get_data_collections(soup: BeautifulSoup) -> List[Dict]:
    ___departure_date = get_all_there_dates(soup)
    ___return_date = get_all_back_dates(soup)
    ___price = get_all_prices(soup)
    attrs = locals().copy()
    collections = []
    for k, v in attrs.items():
        if k.startswith('___'):
            collections.append({k.replace('___', ''): v})
    return collections


def get_soup(url: str, proxy: Dict = None) -> BeautifulSoup:
    response = requests.get(url=url, proxies=proxy)
    page_content = response.content
    return BeautifulSoup(page_content, "html.parser")


def get_url(country_name: str) -> str:
    return getattr(target_countries, country_name)


def get_proxies() -> List[Dict]:
    soup = get_soup('https://www.sslproxies.org')
    rows = soup.find_all('tr')
    proxies = []
    for row in rows:
        all_tds = row.find_all('td')
        try:
            is_ip = all_tds[0].text.count('.') == 3
            if not is_ip:
                continue
        except:
            continue

        ip = all_tds[0].text
        port = all_tds[1].text
        https = all_tds[6].text
        protocol = 'http'
        if https.strip().lower() == 'yes':
            protocol = 'https'
        proxy = {protocol: ip + ':' + port}
        proxies.append(proxy)
    return proxies


def verify_parsing_ok(data_collections: List[Dict]):
    for dc in data_collections:
        if not dc:
            raise ConnectionError("Something went wrong, could't parse a page")


def main():
    country_names = get_all_var_names('countries')
    countries_with_found_flights = []
    exception = None
    trace_back = None

    try:
        proxies = get_proxies()

        for country_name in country_names:
            url = get_url(country_name)
            proxy = random.sample(proxies, 1)[0]
            soup = get_soup(url, proxy)
            data_collections = get_data_collections(soup)
            verify_parsing_ok(data_collections)
            relevant_results = get_relevant_results(data_collections)

            if relevant_results:
                country = Country(country_name, url, relevant_results)
                countries_with_found_flights.append(country)

    except Exception as e:
        exception = e
        trace_back = traceback.format_exc().splitlines()

    if countries_with_found_flights or exception:
        message = get_email_message(countries_with_found_flights, exception, trace_back)
        send_email(message)


if __name__ == '__main__':
    main()
