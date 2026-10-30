d=pd.read_csv('records.csv')
cols=[c for c in d.columns]
print(cols)
ids=['p_2GM4Y6E0QT','p_E16M0W72XT','p_FBXNM8CX45','p_DJC2S9XNAS','p_YVP9748KDV','p_270D437D6S','p_1Z1DHPD5XB','p_FV6AK1FW56','p_XJPZECBH9Q']
for i in ids:
    r=d[d.prototype_id==i]
    if len(r)==0: print(i,'no rows'); continue
    print(i, r.project.iloc[0], r.get('kind').iloc[0], dict(r.test.value_counts()))
    rec=[c for c in cols if c not in ('prototype_id','project','test','value','kind','record_id','owner','source') and r[c].notna().any()]
    print('  recipe:', [str(r[c].iloc[0]) for c in rec], rec[:2])
    print('  means:', r.groupby('test').value.mean().round(3).to_dict(), 'n=',r.groupby('test').value.count().to_dict())