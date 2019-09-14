from datetime import datetime as dt


# departure_from = '01/01/20'
# departure_to = '20/09/20'


departure_from = '01/05/20'
departure_to = '20/06/20'
price_to = 5 * 60

filter_settings = {'departure_from': dt.strptime(departure_from, "%d/%m/%y"),
                   'departure_to': dt.strptime(departure_to, "%d/%m/%y"),
                   'price_to': price_to}
