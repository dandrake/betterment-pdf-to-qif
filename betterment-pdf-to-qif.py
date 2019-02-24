"""
Parse a Betterment statement PDF and produce QIF files for import
into Moneydance or other financial software.

https://github.com/dandrake/betterment-pdf-to-qif
"""

import sys
import subprocess
import re
import datetime
import collections

DEBUG = True
    
mon_to_num = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}

months = mon_to_num.keys()

ticker_to_name = {
    'BNDX': 'Total International Bond ETF',
    'VBR': 'Vanguard Small-Cap Value ETF',
    'VTI': 'Vanguard Total Stock Market ETF',
    'VTV': 'Vanguard Value ETF',
    'LQD': 'iShares iBoxx $ Investment Grade Corporate Bond ETF',
    'VEA': 'FTSE Developed Markets ETF',
    'VWO': 'Vanguard FTSE Emerging Markets ETF',
    'MUB': 'Municipal Bonds ETF',
    'VWOB': 'Vanguard Emerging Markets Government Bond ETF',
    'VOE': 'Vanguard Mid-Cap Value ETF',
    'VTIP': 'Vanguard Short-Term Inflation-Protected Securities ETF',
    'SHV': 'iShares Short Treasury Bond ETF',
    'EMB': 'Emerging Markets Bonds',
    'IEMG': 'iShares Core MSCI Emerging Markets ETF',
    'VCIT': 'Vanguard Intermediate-Term Corporate Bond ETF',
    'TFI': 'SPDR Nuveen Barclays Municipal Bond ETF',
    'SCHF': 'Schwab International Equity ETF',
    'SCHB': 'Schwab U.S. Broad Market ETF',
    'AGG': 'iShares Core Total US Bond Market ETF',
    'IWS': 'iShares Russell Mid-Cap Value ETF',
    'IWN': 'iShares Russell 2000 Value ETF',
    'SCHV': 'Schwab US Large-Cap Value',
}

def parse_dividend_payment(line):
    """
    we look for lines like

    ['May', '7', '2015', 'MUB', 'iShares', 'National', 'AMT-Free', 'Muni', 'Bond', 'ETF', '$0.05']

    date, fund, description, amount
    """
    try:
        ret = {'type': 'div pay'}
        ret['date'] = datetime.date(month=mon_to_num[line[0]],
                                    day=int(line[1]),
                                    year=int(line[2]))
        ret['ticker'] = line[3]
        ret['desc'] = ' '.join(line[4:-1])
        ret['amount'] = line[-1].lstrip('-$').replace(',', '')

        # these are here to raise exceptions if something weird happens
        ticker_to_name[ret['ticker']]
        float(ret['amount'])
    except:
        raise ValueError
    return ret

def dateatstart(line):
    return datetime.date(month=mon_to_num[line[0]],
                         day=int(line[1]),
                         year=int(line[2]))

def tickerindex(line):
    for i, s in enumerate(line):
        try:
            _ = ticker_to_name[s]
            return i
        except KeyError:
            pass
    raise ValueError

def get_date(line):
    """
    look for a date somewhere in the line, return a datetime object or None
    """
    for i, piece in enumerate(line):
        if piece in months:
            return datetime.date(month=mon_to_num[piece],
                                 day=int(line[i+1]),
                                 year=int(line[i+2]))

def parse_other_activity(line):
    """tricky thing here is that you have two kinds of lines:

    ['Jul', '12', '2016', 'Dividend', 'Reinvestment', 'MUB', '$113.77', '0.150', '$17.02', '76.690', '$8,725.07']

    and 

    ['VTIP', '$49.54', '0.204', '$10.11', '33.659', '$1,667.46']

    so we return a dictionary with the keys we can figure out and leave
    it to the caller to track the necessary state.

    Transaction types are "Dividend Reinvestment", "Automatic
    Deposit", "Advisory Fee", and "Rebalance". (Others I'll add later.)

    Returns a dictionary with keys (a subset of!):

    * date: datetime.date object
    * ticker: ticker symbol
    * share_price
    * shares
    * amount
    * type: right now, one of:
        * div buy: buying after a dividend payment
        * buy, sell: buying after a deposit, selling for rebalance
        * fee sell: selling shares to pay advisory fee
        * tlh: buys and sells for a tax loss harvest. Note that after the first
          transaction for a TLH, further ones will be marked as a regular buy or sell.

    We need different selling types; we gather up the "fee sell"s and
    create a fee payment transaction, but for rebalances, we do nothing
    since those will be, well, balanced by purchases.

    Values except the date are all strings.
    """
    try:
        ret = {}
        i = tickerindex(line)

        d = get_date(line)
        if d:
            ret['date'] = d
        
        ret['ticker'] = line[i]
        
        ret['share_price'] = line[i+1].lstrip('$').replace(',', '')
        # QIF files don't include negative amounts; they list
        # everything as positive and use the transaction type to
        # figure out the rest. So if it's not already a "fee sell",
        # look for a minus sign to see if it should be a sell.
        ret['amount'] = line[i+3].replace('$', '').replace(',', '')

        desc = ''.join(line)
        if 'Reinvestment' in desc:
            ret['type'] = 'div buy'
        elif 'Deposit' in desc:
            ret['type'] = 'buy'
        elif 'Fee' in desc:
            ret['type'] = 'fee sell'
        elif 'Harvesting' in desc:
            ret['type'] = 'tlh'
        elif float(ret['amount']) > 0:
            ret['type'] = 'buy'
        else:
            ret['type'] = 'sell'

        # We calculate the number of shares on our own; see
        # discussion in the README.
        ret['shares'] = '{:.6f}'.format(float(ret['amount']) /
                                        float(ret['share_price']))
        if abs(float(ret['shares']) - float(line[i+2])) >= .001:
            print('wonky number of shares:')
            print('PDF says', line[4])
            print('transaction:', ret)

        # check if ticker ok
        ticker_to_name[ret['ticker']]

        return ret
    except Exception as err:
        if DEBUG: print(err)
        raise ValueError

def parse_text(txt):
    """parse the text we get from the statement PDF (as a list of list of
    strings) and return a list of transactions -- dictionaries.
    """
    goal = None
    trans_type = None
    transactions = []
    for linenum, line in enumerate(txt):
        if line[:2] == ['BUILD', 'WEALTH']:
            goal = 'build wealth'
            trans_type = None
            if DEBUG: print('build wealth starts line', linenum) 
        elif line[:2] == ['SAFETY', 'NET']:
            goal = 'safety net'
            trans_type = None
            if DEBUG: print('safety net starts on', linenum) 
        elif line[:3] == 'WORLD CUP 2026'.split():
            goal = 'world cup'
            trans_type = None
            if DEBUG: print('world cup starts on', linenum)
        elif line[:2] == 'SMART SAVER'.split():
            goal = None
            if DEBUG: print('done with goals line', linenum)
        if goal is not None:
            sub_trans_type = None
            if trans_type == 'dividend':
                try:
                    trans = parse_dividend_payment(line)
                    if DEBUG: print('dividend:', trans)
                    trans['goal'] = goal
                    transactions.append(trans)
                except ValueError:
                    pass
            elif trans_type == 'other':
                try:
                    trans = parse_other_activity(line)
                    try:
                        trans_date = trans['date']
                    except KeyError:
                        trans['date'] = trans_date
                    try:
                        # the first advisory fee transaction gets correctly classified
                        # as "fee sell", but after that they're just "sell"; change the type
                        # appropriately
                        if trans['type'] == 'sell' and sub_trans_type == 'fee sell':
                            trans['type'] = 'fee sell'
                        # similar for TLH: first one is marked as 'tlh', further ones are buy or sell
                        elif sub_trans_type == 'tlh':
                            # we'll handle whether it's a buy or sell later
                            trans['type'] = 'tlh'
                            if DEBUG: print('resetting  trans[type]')
                        else:
                            if DEBUG: print('setting sub_trans_type to', trans['type'])
                            sub_trans_type = trans['type']
                    except KeyError:
                        trans['type'] = sub_trans_type

                    if DEBUG: print('other trans:', trans)
                    trans['goal'] = goal
                    transactions.append(trans)
                except ValueError:
                    pass

            if line == ['Dividend', 'Payment', 'Detail']:
                trans_type = 'dividend'
            elif line == ['Quarterly', 'Activity', 'Detail']:
                trans_type = 'other'

    # now we want, as we would say in SQL,
    #   SELECT goal, date, SUM(amount)
    #   WHERE type = 'fee sell'
    #   GROUP BY date;
    # and to add corresponding fee-transfer transactions
    fees = collections.defaultdict(float)
    for trans in [t for t in transactions if t['type'] == 'fee sell']:
        fees[(trans['goal'], trans['date'])] += float(trans['amount'])
    for goal, date in fees.keys():
        transactions.append({'goal': goal,
                             'date': date,
                             'type': 'fee pay',
                             'amount': abs(fees[(goal, date)])})
    return transactions

def fmt_date(t):
    return t['date'].strftime('%m/%d/%Y')

def set_memo(trans):
    trans['memo'] = ''

    if trans['type'] == 'div buy':
        trans['memo'] = 'dividend reinvestment'
    elif 'tlh' in trans['type']:
        trans['memo'] = 'tax loss harvesting'
    if DEBUG and trans['memo'] != '': print('in set_memo, trans: ', trans)

    # later: maybe do allocation change; rebalance; charitable gifts

def create_qif(transactions, fn):
    # the initial space below is necessary!
    hdr = r""" !Account
NBetterment {0}
DBetterment {0}
TInvst
^"""

    buysell = r"""!Type:Invst
D{date}
N{type}
Y{security}
I{price}
Q{num_shares}
T{amount}
M{memo}
O0.00
^"""

    div = r"""!Type:Invst
D{date}
NDiv
Y{security}
T{amount}
O0.00
L[Investment:Dividends]
^"""

    fee = r"""!Type:Invst
D{date}
NXOut
PAdmin Fee
T{amount}
L[Bank Charge:Service Charges]
${amount}
O0.00
^"""

    bw = [hdr.format('Build Wealth')]
    sn = [hdr.format('Safety Net')]
    wc = [hdr.format('World Cup')]

    for trans in transactions:
        if 'div pay' == trans['type']:
            q = div.format(date=fmt_date(trans),
                           security=ticker_to_name[trans['ticker']],
                           amount=trans['amount'])
        elif 'fee pay' == trans['type']:
            q = fee.format(date=fmt_date(trans),
                           amount=trans['amount'])
        else:
            if trans['type'] == 'tlh':
                if DEBUG: print('create_qif:', trans)
                if trans['shares'][0] == '-':
                    trans['type'] = 'tlh sell'
                else:
                    trans['type'] = 'tlh buy'
            
            if 'buy' in trans['type']:
                action = 'Buy'
            elif 'sell' in trans['type']:
                action = 'Sell'
            else:
                print('weird, transaction not dividend, fee, buy, or sell:', trans)
                raise ValueError

            set_memo(trans)

            q = buysell.format(date=fmt_date(trans),
                               type=action,
                               security=ticker_to_name[trans['ticker']],
                               price=trans['share_price'],
                               num_shares=trans['shares'].lstrip('-'),
                               amount=trans['amount'].lstrip('-'),
                               memo=trans['memo'])

        if trans['goal'] == 'safety net':
            sn.append(q)
        elif trans['goal'] == 'build wealth':
            bw.append(q)
        elif trans['goal'] == 'world cup':
            wc.append(q)
        else:
            print('transaction has no goal!', trans)
            raise ValueError

    with open(fn + '-build_wealth.qif', 'w') as bwf:
        bwf.write('\n'.join(bw))
    with open(fn + '-safety_net.qif', 'w') as snf:
        snf.write('\n'.join(sn))
    with open(fn + '-world_cup.qif', 'w') as wcf:
        wcf.write('\n'.join(wc))


def run(fn):
    # we want a list of lines, each split on whitespace
    txt = [line.decode('utf-8') for line in
           subprocess.check_output(['pdftotext', '-nopgbrk', '-layout', 
                                    fn, '-']).splitlines()]

    with open(fn + '-debug.txt', 'w') as f:
        f.write('\n'.join([str(line.split()) for line in txt
                           if not re.match('^\s*$', line)]))

    create_qif(parse_text([line.split() for line in txt
                           if not re.match('^\s*$', line)]),
               fn[:-4])

if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except IndexError:
        pass
