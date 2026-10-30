import pandas as pd
x=pd.read_csv('records.csv'); ids=['p_W3C23XARDY','p_H6M64FVH6S','p_H6M64FVH6V','p_H6M64FVH7B','p_AZ5VDQBF40','p_EFB2ME7Y7X','p_PDDT6X6J04']
q=x[(x.prototype_id.isin(ids))&(x.kind=='qualification')&(x.test=='seal hold temperature')]
print(q.groupby('prototype_id').value.agg(['mean','min','max']))