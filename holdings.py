

def main(filename):

    from betterment import ticker_to_name
    print(ticker_to_name.keys())
    def get_ticker(tokens):
        try:
            if tokens[-7] in ticker_to_name.keys():
                return tokens[-7]
        except IndexError:
            return None

    goals = set(['build wealth', 'safety net', 'world cup'])
    joinline = lambda line: ' '.join(line).lower()
    for line in open(filename):
        tokens = eval(line)
        joined = joinline(tokens)
        if 'acct #' in joined and any(goal in joined for goal in goals):
            print(joined)
        ticker = get_ticker(tokens)
        if ticker is not None:
            name = ' '.join(tokens[0:-7])
            shares = tokens[-2]
            print(f'{ticker},{shares},{name}')

if __name__ == '__main__':
    import sys
    main(sys.argv[1])
        
