import pandas as pd
x=pd.read_csv('records.csv'); z=x[x.prototype_id=='p_H6M64FVH6V']; print(z[['project','prototype_id','kind','test','value','measured_by']].to_string(index=False))