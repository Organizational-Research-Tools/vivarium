import pandas as pd
D=pd.read_csv('records.csv')
for p in ['p_Q0MEGW920C','p_Q0MEGW920E','p_R5TB5PKA0S','p_8M12B6QVE7','p_8M12B6QVE9','p_8M12B6QVEB','p_8M12B6QVED']:
 g=D[D.prototype_id==p]
 print('\n',p, g[['kind','test','value','measured_by']].to_string(index=False) if len(g) else 'NO ROWS')
 if len(g):
  print([D.iloc[0][c] for c in D.columns[10:]])