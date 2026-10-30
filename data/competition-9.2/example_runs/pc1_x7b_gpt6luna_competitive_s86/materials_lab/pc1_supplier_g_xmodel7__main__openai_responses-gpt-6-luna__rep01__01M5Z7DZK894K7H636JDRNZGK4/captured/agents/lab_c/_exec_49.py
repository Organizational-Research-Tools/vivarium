import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.project.eq('QP-9219')]; e=q[q.kind.eq('exploratory')].pivot_table(index='prototype_id',columns='instrument',values='value',aggfunc='mean'); p=q[q.kind.eq('qualification')].pivot_table(index='prototype_id',columns='instrument',values='value',aggfunc='mean');
print('Expl candidates')
print(e.sort_values(['water','strength','heat'],ascending=False).head(25).to_string())
print('\nPanels candidates over all tests')
print(p.sort_values(['water','strength','heat'],ascending=False).head(35).to_string())