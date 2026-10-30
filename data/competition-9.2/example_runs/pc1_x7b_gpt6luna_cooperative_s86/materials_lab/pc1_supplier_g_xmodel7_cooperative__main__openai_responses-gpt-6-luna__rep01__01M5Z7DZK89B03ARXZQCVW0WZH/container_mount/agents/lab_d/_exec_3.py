import pandas as pd, numpy as np
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import RidgeCV, Ridge
from sklearn.model_selection import LeaveOneOut, cross_val_score
D=pd.read_csv('records.csv'); mods=D.columns[11:].tolist()
# mean by proto, test, project
A=D.groupby(['project','prototype_id','test'],as_index=False).agg(value=('value','mean'))
base={'seal hold temperature':77.5,'edge crush resistance':7.1,'wet strength retained':78}
step={'seal hold temperature':.25,'edge crush resistance':.03,'wet strength retained':.4}
# recipe row by proto
recipes=D.drop_duplicates('prototype_id').set_index('prototype_id')[mods]
A=A.join(recipes,on='prototype_id'); A['y']=[(r.value-base[r.test])/step[r.test] for r in A.itertuples()]
enc=OneHotEncoder(handle_unknown='ignore'); X=enc.fit_transform(A[mods]);
for test,g in A.groupby('test'):
 x=enc.transform(g[mods]); y=g.y.to_numpy()
 print(test,len(y),'range',y.min(),y.max())
 for alpha in [.1,1,10,100]:
  m=Ridge(alpha=alpha).fit(x,y); pred=m.predict(x)
  print(alpha,'rmse',np.sqrt(np.mean((pred-y)**2)))
 # per variant effects top relative
 m=Ridge(alpha=1).fit(x,y)
 names=enc.get_feature_names_out()
 impacts=sorted(zip(names,m.coef_),key=lambda kv:-kv[1])
 print('top',impacts[:10])
 print('bottom',impacts[-10:])
