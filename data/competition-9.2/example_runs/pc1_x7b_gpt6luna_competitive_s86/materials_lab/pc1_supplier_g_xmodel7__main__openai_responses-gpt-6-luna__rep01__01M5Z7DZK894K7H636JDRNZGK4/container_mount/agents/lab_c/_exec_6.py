import pandas as pd
D=pd.read_csv('records.csv')
# QP9219 known heat panel means and design, optionally strength/water
s=D[(D.project=='QP-9219')& (D.kind=='qualification')].groupby(['prototype_id','instrument']).value.agg(['mean','std','count']).reset_index()
print(s.to_string(index=False))
print('\nall QP9273?')
print(D[D.project=='QP-9273'].groupby(['prototype_id','instrument']).value.agg(['mean','std','count']))