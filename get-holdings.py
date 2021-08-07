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

DEBUG=True


def parse_file(fn):
    ret = []
    with open(fn) as f:
        for line in f:
            ret.append([_.lower() for _ in eval(line)])
    return ret


def run(fn):
    lines = parse_file(fn)

    goal = None
    in_monthly_overview = False
    doing_holdings = False
    did_parse_shares = False

    for i, line in enumerate(lines):
        if line[0] == 'total':
            break
    print(f'start looking {i}')

    goals = ['buildwealth', 'safetynet', 'worldcup2026']
    holdings = dict((g, dict()) for g in goals)
    for i, line in enumerate(lines[i:]):

        if ''.join(line) in goals:
            goal_index = goals.index(''.join(line))
            goal = goals[goal_index]
            in_monthly_overview = False
            doing_holdings = False
            print(('=' * 50) + f'\n{goal} starts line {i}')
        if goal is not None and 'monthlyoverview' in ''.join(line):
            in_monthly_overview = True
        if line[:3] == ['type', 'description', 'ticker'] and in_monthly_overview:
            doing_holdings = True

        if goal is not None and in_monthly_overview and doing_holdings:
            if line[0] == 'ETFs':
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
                    if DEBUG: print(f"bad num shares '{shares}', doing holdings false")
                    doing_holdings = False
                    did_parse_shares = False
                else:
                    pass # first line after starting, "type, description, ticker"
            else:
                print(f'{num_shares} shares for {desc}')
                ticker = desc[-1].upper()
                if desc[0] == 'etfs':
                    stock_name = ' '.join(desc[1:-1])
                else:
                    stock_name = ' '.join(desc[:-1])
                holdings[goal][ticker] = [num_shares, stock_name]
    return holdings

def get_rows(all_holdings):
    rows = []
    for goal in all_holdings.keys():
        rows.append([f'GOAL: {goal}'])
        rows.append(['Ticker', 'Name', 'Shares'])
        for ticker, details in all_holdings[goal].items():
            rows.append([ticker, ' '.join(details[1:]), str(details[0])])
    return rows
                        
def write_output(fn, lines):
    with open(fn, 'w') as f:
        f.write('\n'.join(','.join(row) for row in row_list))

if __name__ == '__main__':
    holdings = run(sys.argv[1])
    row_list = get_rows(holdings)
    print('=' * 50)
    output_fn = 'got-holdings.csv'
    write_output(output_fn, row_list)
