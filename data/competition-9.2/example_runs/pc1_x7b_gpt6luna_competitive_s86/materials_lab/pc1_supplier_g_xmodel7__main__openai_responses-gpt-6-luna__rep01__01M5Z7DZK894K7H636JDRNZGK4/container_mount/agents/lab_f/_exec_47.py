import pandas as pd
x=pd.read_csv('records.csv'); ids=['p_K6ZM59ZMJT','p_EGTGJGD3PY','p_CEYHT8P45J','p_42VSB15H3X']
y=x[x.prototype_id.isin(ids)]; print(y.groupby(['prototype_id','test','measured_by']).agg(n=('value','size'),mean=('value','mean')).to_string())
