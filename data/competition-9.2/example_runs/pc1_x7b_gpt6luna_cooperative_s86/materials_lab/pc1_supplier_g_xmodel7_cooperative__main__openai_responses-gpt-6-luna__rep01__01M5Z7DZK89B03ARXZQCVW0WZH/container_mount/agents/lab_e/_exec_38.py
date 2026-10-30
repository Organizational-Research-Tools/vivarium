import pandas as pd
x=pd.read_csv('records.csv'); p=x[x.prototype_id.isin(['p_4XN79BMRX8','p_4XN79BMRXA','p_4XN79BMRXC'])];print(p.groupby('prototype_id').value.mean())