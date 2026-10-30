import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.prototype_id.isin(['p_MVYDTC3AAM','p_MVYDTC3AAJ','p_MVYDTC3AAG','p_4AQTFYGQBA'])].to_string(index=False))