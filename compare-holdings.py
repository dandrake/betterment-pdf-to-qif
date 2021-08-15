"""
The ultimate goal here is to export data from Moneydance, then parse the
statement and programatically ensure that all the totals are correct for
each goal. 

To get data out of MD, use the Extract Data extension. That gives a CSV.

Then to get the totals from my statement, use this.

TODO: conceptually, I just need a join between those two, and then to
subtract.


"""


import sys
import csv
from collections import defaultdict
from betterment import ticker_to_name

def normalized_key(goal_):
    goal = goal_.lower()
    if 'build' in goal:
        return 'buildwealth'
    elif 'safety' in goal:
        return 'safetynet'
    elif 'world' in goal:
        return 'worldcup'
    else:
        raise ValueError(f"Cannot normalize goal '{goal_}'.")



class MoneydanceExtractDataParser:
    def __init__(self, csv_filename):
        self.debug = False
        self.holdings = self.get_dict_from_rows(self.get_rows_from_csv(csv_filename))

    def get_rows_from_csv(self, csv_filename):
        rows = []
        with open(csv_filename) as csv_file:
            csv_reader = csv.reader(csv_file)
            for row in csv_reader:
                if row == ['']:
                    return rows
                rows.append(row)
        return rows
    
    def get_dict_from_rows(self, rows):
        holdings = defaultdict(dict)
        header = rows[0]
        symbol_col = header.index('Symbol')
        stock_name_col = header.index('Stock')
        shares_col = header.index('Shares/Units')
        account_col = header.index('Accounts')
        for holding in rows[1:]:
            if self.debug: print(f'{holding[symbol_col]}, {holding[stock_name_col]}, {holding[shares_col]}, {holding[account_col]}')
            holdings[normalized_key(holding[account_col])][holding[symbol_col].lower()] = {'stock_name': holding[stock_name_col],
                                                                   'shares': holding[shares_col]}
        return holdings

class BettermentStatementParser:

    def __init__(self, text_statement_file_name):
        self.debug = False
        self.holdings = self.run(text_statement_file_name)

    
    def parse_file(self, fn):
        ret = []
        with open(fn) as f:
            for line in f:
                ret.append([_.lower() for _ in eval(line)])
        return ret
    
    def run(self, fn):
        lines = self.parse_file(fn)
        goal = None
        in_monthly_overview = False
        doing_holdings = False
        did_parse_shares = False
    
        for i, line in enumerate(lines):
            if line[0] == 'total':
                break
        if self.debug: print(f'start looking {i}')
    
        goals = ['buildwealth', 'safetynet', 'worldcup2026']
        holdings = defaultdict(dict)
        for i, line in enumerate(lines[i:]):

            
            if ''.join(line) in goals:
                goal = normalized_key(''.join(line))
                in_monthly_overview = False
                doing_holdings = False
                if self.debug: print(('=' * 50) + f'\n{goal} starts line {i}')
            if goal is not None and 'monthlyoverview' in ''.join(line):
                in_monthly_overview = True
            if line[:3] == ['type', 'description', 'ticker'] and in_monthly_overview:
                doing_holdings = True
    
            if goal is not None and in_monthly_overview and doing_holdings:
                if line[0] == 'etfs':
                    s = line[1:]
                else:
                    s = line
                desc = s[:-6]
                shares = s[-2]
                try:
                    num_shares = float(shares)
                    did_parse_shares = True
                except ValueError:
                    num_shares = None
                if num_shares is None:
                    if did_parse_shares:
                        if self.debug: print(f"bad num shares '{shares}', doing holdings false")
                        doing_holdings = False
                        did_parse_shares = False
                    else:
                        pass # first line after starting, "type, description, ticker"
                else:
                    if self.debug: print(f'{num_shares} shares for {desc}')
                    ticker = desc[-1]
                    if desc[0] == 'ETFs':
                        stock_name = ' '.join(desc[1:-1])
                    else:
                        stock_name = ' '.join(desc[:-1])
                    holdings[goal][ticker] = {'shares': shares, 'stock_name': stock_name}
        return holdings



class HoldingsComparer:
    def __init__(self, md, bment):
        self.comparisons = self.compare_goals(md, bment)

    def compare_goals(self, md, bment, debug=False):
        comparisons = {}
        for goal in md:
            print(f'{goal=}')
            comparisons[goal] = self.compare_holdings(md[goal], bment[goal])
        return comparisons

    def compare_holdings(self, md_goal, bment_goal):
        tickers = set(md_goal.keys()).union(bment_goal.keys())
        comparisons = {}
        for ticker in tickers:
            try:
                md_shares = md_goal[ticker]['shares']
            except KeyError:
                md_shares = '0'
            try:
                bment_shares = bment_goal[ticker]['shares']
            except KeyError:
                bment_shares = '0'
            diff = float(md_shares) - float(bment_shares)
            print(f'{ticker=}, {md_shares=}, {bment_shares=}, {diff=}')
            comparisons[(abs(diff), ticker)] = {'moneydance': md_shares,
                                               'betterment': bment_shares,
                                               'diff': diff}
        return comparisons



class ComparisonSorter:
    def __init__(self, comparisons):
        self.sorted = self.sort_comparisons(comparisons)

    def sort_comparisons(self, comparisons):
        ret = [['Goal', 'Ticker', 'Moneydance Shares', 'Betterment_Shares', 'Difference', 'Stock Name']]
        for goal in comparisons:
            for key in reversed(sorted(comparisons[goal].keys())):
                _, ticker = key
                ret.append([goal,
                            ticker,
                            comparisons[goal][key]['moneydance'],
                            comparisons[goal][key]['betterment'],
                            comparisons[goal][key]['diff'],
                            ticker_to_name[ticker]])
        return ret
                

class ComparisonWriter:
    def __init__(self, rows, output_filename):
        with open(output_filename, 'w') as outfile:
            csv_writer = csv.writer(outfile)
            for row in rows:
                csv_writer.writerow(row)
                

if __name__ == '__main__':

    md_holdings = MoneydanceExtractDataParser(sys.argv[2]).holdings
    bment_holdings = BettermentStatementParser(sys.argv[1]).holdings
    comparer = HoldingsComparer(md_holdings, bment_holdings)
    rows = ComparisonSorter(comparer.comparisons).sorted
    ComparisonWriter(rows, 'compared.csv')
    
    
