import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project=='QP-9980') & x.prototype_id.isin(['p_ZDYAYEX9A4','p_ZDYAYEX9A6','p_ZDYAYEX9A8','p_ZDYAYEX9AA','p_EZR46XFBA9','p_EZR46XFBAB','p_EZR46XFBAF'])]
print(q.groupby('prototype_id').value.agg(['mean','min','max']).to_string())