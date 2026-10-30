import pandas as pd
x=pd.read_csv('records.csv'); x=x[x.kind=='qualification']; g=x.groupby(['project','prototype_id','test']).value.agg(['mean','count']).reset_index();
for proj in sorted(g.project.unique()):
 print('\n',proj)
 print(g[g.project==proj].sort_values('mean',ascending=False).groupby('test').head(8)[['prototype_id','test','mean','count']].sort_values(['test','mean'],ascending=[True,False]).to_string(index=False))