<!-- Извлечено из Product-part/01_Входящие/homework_examples/data_science/Пример домашки 1. (АА)/Хорошее решение.html скриптом api/scripts/extract_homework.py. Не редактировать вручную. -->

tracking

Ноутбук для семинара Трекинг экспериментов¶

Сегодня мы:

рассмотрим пайплайн подготовки данных и обучения модели классификации доходов

создадим эксперимент в MLflow и настроим логирование:
параметров

метрик

моделей

артефактов

проведём серию запусков с изменением параметров и сравним результаты в UI MLflow

In [991]:

# !pip install numpy datasets scikit-learn mlflow==2.22.1

Импорты¶

In [992]:

# импорты для пайплайна

import numpy as np
from datasets import load_dataset
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, recall_score, precision_score, precision_recall_curve, auc
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from catboost import CatBoostClassifier, Pool
import matplotlib.pyplot as plt

In [993]:

import sklearn
import numpy
import datasets
import catboost
import matplotlib
import mlflow

numpy.__version__, sklearn.__version__, catboost.__version__, datasets.__version__, matplotlib.__version__, mlflow.__version__

Out[993]:

('2.3.0', '1.8.0', '1.2.8', '4.0.0', '3.10.8', '2.22.1')

In [994]:

mlflow.set_tracking_uri("http://158.160.242.172:5000/")

In [995]:

mlflow.set_experiment(experiment_name="homework-mnkochnov.ext")

Out[995]:

<Experiment: artifact_location='mlflow-artifacts:/6', creation_time=1776271096006, experiment_id='6', last_update_time=1776271096006, lifecycle_stage='active', name='homework-mnkochnov.ext', tags={}>

Константы¶

In [996]:

DATASET_NAME = "scikit-learn/adult-census-income"
TEST_SIZE = 0.3
RANDOM_STATE = 42

Скачивание и подготовка данных¶

Скачаем данные

In [997]:

dataset = load_dataset(DATASET_NAME)

Посмотрим на них и изучим

In [998]:

dataset

Out[998]:

DatasetDict({
 train: Dataset({
 features: ['age', 'workclass', 'fnlwgt', 'education', 'education.num', 'marital.status', 'occupation', 'relationship', 'race', 'sex', 'capital.gain', 'capital.loss', 'hours.per.week', 'native.country', 'income'],
 num_rows: 32561
 })
})

In [999]:

dataset["train"].features

Out[999]:

{'age': Value('int64'),
 'workclass': Value('string'),
 'fnlwgt': Value('int64'),
 'education': Value('string'),
 'education.num': Value('int64'),
 'marital.status': Value('string'),
 'occupation': Value('string'),
 'relationship': Value('string'),
 'race': Value('string'),
 'sex': Value('string'),
 'capital.gain': Value('int64'),
 'capital.loss': Value('int64'),
 'hours.per.week': Value('int64'),
 'native.country': Value('string'),
 'income': Value('string')}

In [1000]:

df = dataset["train"].to_pandas()
df

Out[1000]:

age
workclass
fnlwgt
education
education.num
marital.status
occupation
relationship
race
sex
capital.gain
capital.loss
hours.per.week
native.country
income

0
90
?
77053
HS-grad
9
Widowed
?
Not-in-family
White
Female
0
4356
40
United-States
<=50K

1
82
Private
132870
HS-grad
9
Widowed
Exec-managerial
Not-in-family
White
Female
0
4356
18
United-States
<=50K

2
66
?
186061
Some-college
10
Widowed
?
Unmarried
Black
Female
0
4356
40
United-States
<=50K

3
54
Private
140359
7th-8th
4
Divorced
Machine-op-inspct
Unmarried
White
Female
0
3900
40
United-States
<=50K

4
41
Private
264663
Some-college
10
Separated
Prof-specialty
Own-child
White
Female
0
3900
40
United-States
<=50K

...

32556
22
Private
310152
Some-college
10
Never-married
Protective-serv
Not-in-family
White
Male
0
40
United-States
<=50K

32557
27
Private
257302
Assoc-acdm
12
Married-civ-spouse
Tech-support
Wife
White
Female
0
38
United-States
<=50K

32558
40
Private
154374
HS-grad
9
Married-civ-spouse
Machine-op-inspct
Husband
White
Male
0
40
United-States
>50K

32559
58
Private
151910
HS-grad
9
Widowed
Adm-clerical
Unmarried
White
Female
0
40
United-States
<=50K

32560
22
Private
201490
HS-grad
9
Never-married
Adm-clerical
Own-child
White
Male
0
20
United-States
<=50K

32561 rows × 15 columns

Описание признаков:

age — возраст человека

workclass — тип занятости

fnlwgt — вес наблюдения в данных переписи населения США (сколько реальных людей в популяции «представляет» эта строка)

education — образование

education.num — уровень образования в виде числа

marital.status — семейное положение

occupation — профессия / род деятельности

relationship — роль человека в семье

race — расовая группа

sex — пол человека (Male / Female)

capital.gain — доход от капитала (прибыль от продажи активов)

capital.loss — убытки от капитала

hours.per.week — количество рабочих часов в неделю

native.country — страна происхождения

Описание таргета:

income — бинарно, получает человек больше 50k $ в год или нет

Оставим только часть признаков

In [1001]:

columns = ["age", "workclass", "education.num", "occupation", "marital.status", "sex", "capital.gain", "capital.loss", "hours.per.week"]

target_column = "income"

И разделим датафрейм на признаки и таргет

In [1002]:

X, y = df[columns], df[target_column]

In [1003]:

X

Out[1003]:

age
workclass
education.num
occupation
marital.status
sex
capital.gain
capital.loss
hours.per.week

0
90
?
9
?
Widowed
Female
0
4356
40

1
82
Private
9
Exec-managerial
Widowed
Female
0
4356
18

2
66
?
10
?
Widowed
Female
0
4356
40

3
54
Private
4
Machine-op-inspct
Divorced
Female
0
3900
40

4
41
Private
10
Prof-specialty
Separated
Female
0
3900
40

...

32556
22
Private
10
Protective-serv
Never-married
Male
0
40

32557
27
Private
12
Tech-support
Married-civ-spouse
Female
0
38

32558
40
Private
9
Machine-op-inspct
Married-civ-spouse
Male
0
40

32559
58
Private
9
Adm-clerical
Widowed
Female
0
40

32560
22
Private
9
Adm-clerical
Never-married
Male
0
20

32561 rows × 9 columns

In [1004]:

y

Out[1004]:

0 <=50K
1 <=50K
2 <=50K
3 <=50K
4 <=50K
 ...
32556 <=50K
32557 <=50K
32558 >50K
32559 <=50K
32560 <=50K
Name: income, Length: 32561, dtype: object

Используем Label Encoding для кодирования категориальных признаков

In [1005]:

cat_features = ["workclass", "occupation", "marital.status", "sex"]
num_features = list(set(columns) - set(cat_features))

In [1006]:

preprocessor = ColumnTransformer(
 transformers=[
 ("cat", OrdinalEncoder(), cat_features),
 ("num", StandardScaler(), num_features),
 ]
)

И закодируем целевую переменную

In [1007]:

y_transformed = (y == ">50K").astype(int)

In [1008]:

y_transformed

Out[1008]:

0 0
1 0
2 0
3 0
4 0
 ..
32556 0
32557 0
32558 1
32559 0
32560 0
Name: income, Length: 32561, dtype: int64

In [1009]:

y_transformed.value_counts().plot.bar();

Разделим на train и test

In [1010]:

X_train, X_test, y_train, y_test = train_test_split(X, y_transformed, test_size=TEST_SIZE, random_state=RANDOM_STATE)

In [1011]:

X_train.shape, X_test.shape, y_train.shape, y_test.shape

Out[1011]:

((22792, 9), (9769, 9), (22792,), (9769,))

Обучение модели¶

В качестве бейзлайна возьмём логистическую регрессию

In [1012]:

exp_name = "best_catboost"

In [1013]:

# lr_params = {"penalty": "l2", "C": 1, "solver": "lbfgs", "max_iter": 1000}

In [ ]:

# logreg = LogisticRegression(**lr_params, random_state=RANDOM_STATE)
# logreg

In [1015]:

# rf_params = {"n_estimators": 100, "criterion": "log_loss", "max_depth": 15, "min_samples_split": 10}

In [1016]:

# rf = RandomForestClassifier(**rf_params, random_state=RANDOM_STATE)

In [1017]:

cb_params = {'learning_rate': 0.1, 'depth': 5, 'early_stopping_rounds': 20}

In [1018]:

cb = CatBoostClassifier(**cb_params, eval_metric="AUC", use_best_model=True, random_state=RANDOM_STATE)

In [1019]:

train_pool = Pool(data=X_train, label=y_train, cat_features=cat_features, feature_names=list(X_train.columns))
test_pool = Pool(data=X_test, label=y_test, cat_features=cat_features, feature_names=list(X_test.columns))

In [1020]:

cb.fit(
 train_pool,
 eval_set=test_pool,
)

0: test: 0.8729696 best: 0.8729696 (0) total: 32.4ms remaining: 32.4s
1: test: 0.8811215 best: 0.8811215 (1) total: 55.5ms remaining: 27.7s
2: test: 0.8857677 best: 0.8857677 (2) total: 77.4ms remaining: 25.7s
3: test: 0.8915744 best: 0.8915744 (3) total: 95ms remaining: 23.7s
4: test: 0.8942436 best: 0.8942436 (4) total: 115ms remaining: 22.8s
5: test: 0.8976912 best: 0.8976912 (5) total: 130ms remaining: 21.6s
6: test: 0.9022164 best: 0.9022164 (6) total: 152ms remaining: 21.5s
7: test: 0.9029170 best: 0.9029170 (7) total: 170ms remaining: 21.1s
8: test: 0.9037445 best: 0.9037445 (8) total: 189ms remaining: 20.8s
9: test: 0.9044575 best: 0.9044575 (9) total: 208ms remaining: 20.6s
10: test: 0.9051028 best: 0.9051028 (10) total: 234ms remaining: 21.1s
11: test: 0.9061948 best: 0.9061948 (11) total: 271ms remaining: 22.3s
12: test: 0.9065523 best: 0.9065523 (12) total: 306ms remaining: 23.2s
13: test: 0.9071208 best: 0.9071208 (13) total: 338ms remaining: 23.8s
14: test: 0.9080032 best: 0.9080032 (14) total: 369ms remaining: 24.2s
15: test: 0.9083168 best: 0.9083168 (15) total: 393ms remaining: 24.2s
16: test: 0.9086215 best: 0.9086215 (16) total: 416ms remaining: 24.1s
17: test: 0.9092410 best: 0.9092410 (17) total: 441ms remaining: 24.1s
18: test: 0.9093926 best: 0.9093926 (18) total: 463ms remaining: 23.9s
19: test: 0.9098931 best: 0.9098931 (19) total: 493ms remaining: 24.2s
20: test: 0.9103864 best: 0.9103864 (20) total: 514ms remaining: 23.9s
21: test: 0.9108934 best: 0.9108934 (21) total: 538ms remaining: 23.9s
22: test: 0.9109481 best: 0.9109481 (22) total: 558ms remaining: 23.7s
23: test: 0.9110795 best: 0.9110795 (23) total: 577ms remaining: 23.5s
24: test: 0.9117715 best: 0.9117715 (24) total: 597ms remaining: 23.3s
25: test: 0.9119033 best: 0.9119033 (25) total: 615ms remaining: 23.1s
26: test: 0.9118924 best: 0.9119033 (25) total: 640ms remaining: 23.1s
27: test: 0.9122547 best: 0.9122547 (27) total: 662ms remaining: 23s
28: test: 0.9129569 best: 0.9129569 (28) total: 686ms remaining: 23s
29: test: 0.9134301 best: 0.9134301 (29) total: 712ms remaining: 23s
30: test: 0.9139143 best: 0.9139143 (30) total: 740ms remaining: 23.1s
31: test: 0.9142950 best: 0.9142950 (31) total: 755ms remaining: 22.9s
32: test: 0.9145985 best: 0.9145985 (32) total: 781ms remaining: 22.9s
33: test: 0.9148540 best: 0.9148540 (33) total: 809ms remaining: 23s
34: test: 0.9153549 best: 0.9153549 (34) total: 833ms remaining: 23s
35: test: 0.9164599 best: 0.9164599 (35) total: 851ms remaining: 22.8s
36: test: 0.9166387 best: 0.9166387 (36) total: 871ms remaining: 22.7s
37: test: 0.9168418 best: 0.9168418 (37) total: 887ms remaining: 22.5s
38: test: 0.9169748 best: 0.9169748 (38) total: 906ms remaining: 22.3s
39: test: 0.9170755 best: 0.9170755 (39) total: 925ms remaining: 22.2s
40: test: 0.9172349 best: 0.9172349 (40) total: 942ms remaining: 22s
41: test: 0.9174479 best: 0.9174479 (41) total: 964ms remaining: 22s
42: test: 0.9175712 best: 0.9175712 (42) total: 985ms remaining: 21.9s
43: test: 0.9177898 best: 0.9177898 (43) total: 1.01s remaining: 21.9s
44: test: 0.9180931 best: 0.9180931 (44) total: 1.03s remaining: 21.8s

45: test: 0.9183161 best: 0.9183161 (45) total: 1.05s remaining: 21.8s
46: test: 0.9185598 best: 0.9185598 (46) total: 1.07s remaining: 21.8s
47: test: 0.9186602 best: 0.9186602 (47) total: 1.1s remaining: 21.8s
48: test: 0.9187040 best: 0.9187040 (48) total: 1.12s remaining: 21.7s
49: test: 0.9188229 best: 0.9188229 (49) total: 1.14s remaining: 21.6s
50: test: 0.9191726 best: 0.9191726 (50) total: 1.16s remaining: 21.6s
51: test: 0.9193303 best: 0.9193303 (51) total: 1.22s remaining: 22.2s
52: test: 0.9194472 best: 0.9194472 (52) total: 1.26s remaining: 22.5s
53: test: 0.9195385 best: 0.9195385 (53) total: 1.3s remaining: 22.7s
54: test: 0.9195352 best: 0.9195385 (53) total: 1.32s remaining: 22.7s
55: test: 0.9196818 best: 0.9196818 (55) total: 1.34s remaining: 22.7s
56: test: 0.9197110 best: 0.9197110 (56) total: 1.37s remaining: 22.6s
57: test: 0.9198409 best: 0.9198409 (57) total: 1.4s remaining: 22.7s
58: test: 0.9199594 best: 0.9199594 (58) total: 1.43s remaining: 22.7s
59: test: 0.9200200 best: 0.9200200 (59) total: 1.45s remaining: 22.6s
60: test: 0.9201333 best: 0.9201333 (60) total: 1.47s remaining: 22.6s
61: test: 0.9202028 best: 0.9202028 (61) total: 1.49s remaining: 22.6s
62: test: 0.9203786 best: 0.9203786 (62) total: 1.52s remaining: 22.6s
63: test: 0.9209485 best: 0.9209485 (63) total: 1.54s remaining: 22.6s
64: test: 0.9210316 best: 0.9210316 (64) total: 1.57s remaining: 22.5s
65: test: 0.9210915 best: 0.9210915 (65) total: 1.6s remaining: 22.7s
66: test: 0.9212154 best: 0.9212154 (66) total: 1.62s remaining: 22.6s
67: test: 0.9212601 best: 0.9212601 (67) total: 1.64s remaining: 22.5s
68: test: 0.9213502 best: 0.9213502 (68) total: 1.66s remaining: 22.4s
69: test: 0.9214665 best: 0.9214665 (69) total: 1.68s remaining: 22.3s
70: test: 0.9214896 best: 0.9214896 (70) total: 1.7s remaining: 22.3s
71: test: 0.9219456 best: 0.9219456 (71) total: 1.73s remaining: 22.2s
72: test: 0.9220716 best: 0.9220716 (72) total: 1.75s remaining: 22.2s
73: test: 0.9222324 best: 0.9222324 (73) total: 1.77s remaining: 22.1s
74: test: 0.9222513 best: 0.9222513 (74) total: 1.78s remaining: 22s
75: test: 0.9223703 best: 0.9223703 (75) total: 1.8s remaining: 21.9s
76: test: 0.9225215 best: 0.9225215 (76) total: 1.81s remaining: 21.7s
77: test: 0.9225846 best: 0.9225846 (77) total: 1.83s remaining: 21.7s
78: test: 0.9225820 best: 0.9225846 (77) total: 1.86s remaining: 21.7s
79: test: 0.9227017 best: 0.9227017 (79) total: 1.9s remaining: 21.8s
80: test: 0.9227221 best: 0.9227221 (80) total: 1.93s remaining: 21.9s
81: test: 0.9228011 best: 0.9228011 (81) total: 1.96s remaining: 21.9s
82: test: 0.9230774 best: 0.9230774 (82) total: 1.99s remaining: 22s
83: test: 0.9231770 best: 0.9231770 (83) total: 2.02s remaining: 22.1s
84: test: 0.9232827 best: 0.9232827 (84) total: 2.06s remaining: 22.2s
85: test: 0.9232748 best: 0.9232827 (84) total: 2.08s remaining: 22.1s
86: test: 0.9233288 best: 0.9233288 (86) total: 2.1s remaining: 22s
87: test: 0.9234751 best: 0.9234751 (87) total: 2.12s remaining: 22s
88: test: 0.9235176 best: 0.9235176 (88) total: 2.14s remaining: 21.9s
89: test: 0.9235210 best: 0.9235210 (89) total: 2.17s remaining: 21.9s
90: test: 0.9236072 best: 0.9236072 (90) total: 2.2s remaining: 21.9s
91: test: 0.9236599 best: 0.9236599 (91) total: 2.22s remaining: 21.9s
92: test: 0.9237116 best: 0.9237116 (92) total: 2.25s remaining: 21.9s
93: test: 0.9240058 best: 0.9240058 (93) total: 2.27s remaining: 21.9s
94: test: 0.9241005 best: 0.9241005 (94) total: 2.29s remaining: 21.8s
95: test: 0.9241246 best: 0.9241246 (95) total: 2.32s remaining: 21.8s
96: test: 0.9241336 best: 0.9241336 (96) total: 2.35s remaining: 21.9s
97: test: 0.9243927 best: 0.9243927 (97) total: 2.38s remaining: 21.9s
98: test: 0.9252752 best: 0.9252752 (98) total: 2.41s remaining: 22s
99: test: 0.9253207 best: 0.9253207 (99) total: 2.45s remaining: 22s
100: test: 0.9253599 best: 0.9253599 (100) total: 2.48s remaining: 22.1s
101: test: 0.9254753 best: 0.9254753 (101) total: 2.52s remaining: 22.2s
102: test: 0.9255647 best: 0.9255647 (102) total: 2.55s remaining: 22.2s
103: test: 0.9258318 best: 0.9258318 (103) total: 2.59s remaining: 22.3s
104: test: 0.9258851 best: 0.9258851 (104) total: 2.61s remaining: 22.3s
105: test: 0.9259332 best: 0.9259332 (105) total: 2.64s remaining: 22.2s
106: test: 0.9260144 best: 0.9260144 (106) total: 2.66s remaining: 22.2s
107: test: 0.9260099 best: 0.9260144 (106) total: 2.68s remaining: 22.2s
108: test: 0.9260272 best: 0.9260272 (108) total: 2.7s remaining: 22.1s
109: test: 0.9263060 best: 0.9263060 (109) total: 2.72s remaining: 22s
110: test: 0.9263072 best: 0.9263072 (110) total: 2.74s remaining: 21.9s
111: test: 0.9263716 best: 0.9263716 (111) total: 2.76s remaining: 21.9s
112: test: 0.9263713 best: 0.9263716 (111) total: 2.78s remaining: 21.8s
113: test: 0.9263662 best: 0.9263716 (111) total: 2.79s remaining: 21.7s
114: test: 0.9267176 best: 0.9267176 (114) total: 2.82s remaining: 21.7s
115: test: 0.9268435 best: 0.9268435 (115) total: 2.85s remaining: 21.7s
116: test: 0.9268656 best: 0.9268656 (116) total: 2.87s remaining: 21.7s
117: test: 0.9271648 best: 0.9271648 (117) total: 2.9s remaining: 21.7s
118: test: 0.9271456 best: 0.9271648 (117) total: 2.92s remaining: 21.6s
119: test: 0.9273288 best: 0.9273288 (119) total: 2.94s remaining: 21.6s
120: test: 0.9273842 best: 0.9273842 (120) total: 2.96s remaining: 21.5s
121: test: 0.9276499 best: 0.9276499 (121) total: 2.99s remaining: 21.5s
122: test: 0.9276635 best: 0.9276635 (122) total: 3.02s remaining: 21.5s
123: test: 0.9276666 best: 0.9276666 (123) total: 3.05s remaining: 21.6s
124: test: 0.9278358 best: 0.9278358 (124) total: 3.08s remaining: 21.6s
125: test: 0.9278504 best: 0.9278504 (125) total: 3.11s remaining: 21.6s
126: test: 0.9279156 best: 0.9279156 (126) total: 3.13s remaining: 21.5s
127: test: 0.9279189 best: 0.9279189 (127) total: 3.16s remaining: 21.5s
128: test: 0.9278995 best: 0.9279189 (127) total: 3.19s remaining: 21.5s
129: test: 0.9278980 best: 0.9279189 (127) total: 3.21s remaining: 21.5s
130: test: 0.9278862 best: 0.9279189 (127) total: 3.24s remaining: 21.5s
131: test: 0.9280708 best: 0.9280708 (131) total: 3.27s remaining: 21.5s
132: test: 0.9280963 best: 0.9280963 (132) total: 3.29s remaining: 21.5s
133: test: 0.9281285 best: 0.9281285 (133) total: 3.31s remaining: 21.4s
134: test: 0.9281882 best: 0.9281882 (134) total: 3.35s remaining: 21.4s
135: test: 0.9282305 best: 0.9282305 (135) total: 3.37s remaining: 21.4s
136: test: 0.9284501 best: 0.9284501 (136) total: 3.4s remaining: 21.4s
137: test: 0.9284570 best: 0.9284570 (137) total: 3.43s remaining: 21.4s
138: test: 0.9284734 best: 0.9284734 (138) total: 3.46s remaining: 21.4s
139: test: 0.9284885 best: 0.9284885 (139) total: 3.48s remaining: 21.4s
140: test: 0.9284858 best: 0.9284885 (139) total: 3.51s remaining: 21.4s
141: test: 0.9284859 best: 0.9284885 (139) total: 3.53s remaining: 21.4s
142: test: 0.9284982 best: 0.9284982 (142) total: 3.55s remaining: 21.3s
143: test: 0.9284909 best: 0.9284982 (142) total: 3.57s remaining: 21.2s
144: test: 0.9285063 best: 0.9285063 (144) total: 3.59s remaining: 21.2s
145: test: 0.9285127 best: 0.9285127 (145) total: 3.61s remaining: 21.1s
146: test: 0.9285986 best: 0.9285986 (146) total: 3.63s remaining: 21.1s
147: test: 0.9285990 best: 0.9285990 (147) total: 3.65s remaining: 21s
148: test: 0.9287102 best: 0.9287102 (148) total: 3.67s remaining: 21s
149: test: 0.9287384 best: 0.9287384 (149) total: 3.69s remaining: 20.9s
150: test: 0.9287392 best: 0.9287392 (150) total: 3.7s remaining: 20.8s
151: test: 0.9287683 best: 0.9287683 (151) total: 3.72s remaining: 20.8s
152: test: 0.9287908 best: 0.9287908 (152) total: 3.75s remaining: 20.8s
153: test: 0.9288078 best: 0.9288078 (153) total: 3.77s remaining: 20.7s
154: test: 0.9288458 best: 0.9288458 (154) total: 3.78s remaining: 20.6s
155: test: 0.9288547 best: 0.9288547 (155) total: 3.8s remaining: 20.6s
156: test: 0.9288351 best: 0.9288547 (155) total: 3.83s remaining: 20.5s
157: test: 0.9289526 best: 0.9289526 (157) total: 3.85s remaining: 20.5s
158: test: 0.9289440 best: 0.9289526 (157) total: 3.88s remaining: 20.5s
159: test: 0.9289423 best: 0.9289526 (157) total: 3.9s remaining: 20.5s
160: test: 0.9289224 best: 0.9289526 (157) total: 3.91s remaining: 20.4s
161: test: 0.9289418 best: 0.9289526 (157) total: 3.93s remaining: 20.3s
162: test: 0.9289522 best: 0.9289526 (157) total: 3.95s remaining: 20.3s
163: test: 0.9289815 best: 0.9289815 (163) total: 3.97s remaining: 20.2s
164: test: 0.9289866 best: 0.9289866 (164) total: 3.98s remaining: 20.1s
165: test: 0.9289772 best: 0.9289866 (164) total: 4.01s remaining: 20.1s
166: test: 0.9290203 best: 0.9290203 (166) total: 4.03s remaining: 20.1s
167: test: 0.9290458 best: 0.9290458 (167) total: 4.05s remaining: 20.1s
168: test: 0.9290439 best: 0.9290458 (167) total: 4.07s remaining: 20s
169: test: 0.9290639 best: 0.9290639 (169) total: 4.09s remaining: 20s
170: test: 0.9290914 best: 0.9290914 (170) total: 4.12s remaining: 20s
171: test: 0.9290897 best: 0.9290914 (170) total: 4.13s remaining: 19.9s
172: test: 0.9291547 best: 0.9291547 (172) total: 4.16s remaining: 19.9s
173: test: 0.9291896 best: 0.9291896 (173) total: 4.18s remaining: 19.8s
174: test: 0.9292324 best: 0.9292324 (174) total: 4.2s remaining: 19.8s
175: test: 0.9292318 best: 0.9292324 (174) total: 4.22s remaining: 19.8s
176: test: 0.9293062 best: 0.9293062 (176) total: 4.25s remaining: 19.7s
177: test: 0.9292984 best: 0.9293062 (176) total: 4.27s remaining: 19.7s
178: test: 0.9292886 best: 0.9293062 (176) total: 4.3s remaining: 19.7s
179: test: 0.9292931 best: 0.9293062 (176) total: 4.33s remaining: 19.7s
180: test: 0.9293941 best: 0.9293941 (180) total: 4.37s remaining: 19.8s
181: test: 0.9293867 best: 0.9293941 (180) total: 4.41s remaining: 19.8s
182: test: 0.9294060 best: 0.9294060 (182) total: 4.44s remaining: 19.8s
183: test: 0.9294213 best: 0.9294213 (183) total: 4.47s remaining: 19.8s
184: test: 0.9294175 best: 0.9294213 (183) total: 4.49s remaining: 19.8s
185: test: 0.9294199 best: 0.9294213 (183) total: 4.51s remaining: 19.7s
186: test: 0.9294232 best: 0.9294232 (186) total: 4.53s remaining: 19.7s
187: test: 0.9293790 best: 0.9294232 (186) total: 4.54s remaining: 19.6s
188: test: 0.9293963 best: 0.9294232 (186) total: 4.56s remaining: 19.6s
189: test: 0.9293963 best: 0.9294232 (186) total: 4.58s remaining: 19.5s
190: test: 0.9294416 best: 0.9294416 (190) total: 4.6s remaining: 19.5s
191: test: 0.9294407 best: 0.9294416 (190) total: 4.62s remaining: 19.4s
192: test: 0.9294442 best: 0.9294442 (192) total: 4.64s remaining: 19.4s
193: test: 0.9294603 best: 0.9294603 (193) total: 4.67s remaining: 19.4s
194: test: 0.9294843 best: 0.9294843 (194) total: 4.7s remaining: 19.4s
195: test: 0.9294952 best: 0.9294952 (195) total: 4.72s remaining: 19.4s
196: test: 0.9294954 best: 0.9294954 (196) total: 4.74s remaining: 19.3s
197: test: 0.9295115 best: 0.9295115 (197) total: 4.76s remaining: 19.3s
198: test: 0.9294766 best: 0.9295115 (197) total: 4.79s remaining: 19.3s
199: test: 0.9294645 best: 0.9295115 (197) total: 4.82s remaining: 19.3s
200: test: 0.9294934 best: 0.9295115 (197) total: 4.84s remaining: 19.2s
201: test: 0.9294731 best: 0.9295115 (197) total: 4.86s remaining: 19.2s
202: test: 0.9294667 best: 0.9295115 (197) total: 4.88s remaining: 19.1s
203: test: 0.9294620 best: 0.9295115 (197) total: 4.89s remaining: 19.1s
204: test: 0.9294681 best: 0.9295115 (197) total: 4.91s remaining: 19.1s
205: test: 0.9295195 best: 0.9295195 (205) total: 4.94s remaining: 19s
206: test: 0.9295248 best: 0.9295248 (206) total: 4.96s remaining: 19s
207: test: 0.9295259 best: 0.9295259 (207) total: 4.99s remaining: 19s
208: test: 0.9295730 best: 0.9295730 (208) total: 5.02s remaining: 19s
209: test: 0.9295863 best: 0.9295863 (209) total: 5.04s remaining: 19s
210: test: 0.9295951 best: 0.9295951 (210) total: 5.07s remaining: 19s
211: test: 0.9296075 best: 0.9296075 (211) total: 5.11s remaining: 19s
212: test: 0.9296183 best: 0.9296183 (212) total: 5.13s remaining: 19s
213: test: 0.9296470 best: 0.9296470 (213) total: 5.16s remaining: 19s
214: test: 0.9296721 best: 0.9296721 (214) total: 5.19s remaining: 19s
215: test: 0.9296572 best: 0.9296721 (214) total: 5.23s remaining: 19s
216: test: 0.9296188 best: 0.9296721 (214) total: 5.27s remaining: 19s
217: test: 0.9296473 best: 0.9296721 (214) total: 5.32s remaining: 19.1s
218: test: 0.9296436 best: 0.9296721 (214) total: 5.35s remaining: 19.1s
219: test: 0.9296399 best: 0.9296721 (214) total: 5.38s remaining: 19.1s
220: test: 0.9296458 best: 0.9296721 (214) total: 5.41s remaining: 19.1s
221: test: 0.9296734 best: 0.9296734 (221) total: 5.44s remaining: 19.1s
222: test: 0.9296709 best: 0.9296734 (221) total: 5.47s remaining: 19.1s
223: test: 0.9297093 best: 0.9297093 (223) total: 5.51s remaining: 19.1s
224: test: 0.9297147 best: 0.9297147 (224) total: 5.54s remaining: 19.1s
225: test: 0.9297126 best: 0.9297147 (224) total: 5.57s remaining: 19.1s
226: test: 0.9297212 best: 0.9297212 (226) total: 5.59s remaining: 19.1s
227: test: 0.9297245 best: 0.9297245 (227) total: 5.62s remaining: 19s
228: test: 0.9297453 best: 0.9297453 (228) total: 5.63s remaining: 19s
229: test: 0.9297556 best: 0.9297556 (229) total: 5.67s remaining: 19s
230: test: 0.9297429 best: 0.9297556 (229) total: 5.7s remaining: 19s
231: test: 0.9297509 best: 0.9297556 (229) total: 5.73s remaining: 19s
232: test: 0.9298108 best: 0.9298108 (232) total: 5.77s remaining: 19s
233: test: 0.9298108 best: 0.9298108 (232) total: 5.8s remaining: 19s
234: test: 0.9298668 best: 0.9298668 (234) total: 5.83s remaining: 19s
235: test: 0.9298220 best: 0.9298668 (234) total: 5.85s remaining: 18.9s
236: test: 0.9298196 best: 0.9298668 (234) total: 5.87s remaining: 18.9s
237: test: 0.9298323 best: 0.9298668 (234) total: 5.89s remaining: 18.9s
238: test: 0.9298300 best: 0.9298668 (234) total: 5.9s remaining: 18.8s
239: test: 0.9298255 best: 0.9298668 (234) total: 5.92s remaining: 18.7s
240: test: 0.9298146 best: 0.9298668 (234) total: 5.93s remaining: 18.7s
241: test: 0.9298192 best: 0.9298668 (234) total: 5.96s remaining: 18.7s
242: test: 0.9298373 best: 0.9298668 (234) total: 5.97s remaining: 18.6s
243: test: 0.9299118 best: 0.9299118 (243) total: 5.99s remaining: 18.5s
244: test: 0.9299139 best: 0.9299139 (244) total: 6s remaining: 18.5s
245: test: 0.9299138 best: 0.9299139 (244) total: 6.02s remaining: 18.4s
246: test: 0.9299302 best: 0.9299302 (246) total: 6.03s remaining: 18.4s
247: test: 0.9299482 best: 0.9299482 (247) total: 6.05s remaining: 18.4s
248: test: 0.9299666 best: 0.9299666 (248) total: 6.09s remaining: 18.4s
249: test: 0.9299989 best: 0.9299989 (249) total: 6.12s remaining: 18.3s
250: test: 0.9300004 best: 0.9300004 (250) total: 6.15s remaining: 18.4s
251: test: 0.9299955 best: 0.9300004 (250) total: 6.19s remaining: 18.4s
252: test: 0.9299819 best: 0.9300004 (250) total: 6.24s remaining: 18.4s
253: test: 0.9300076 best: 0.9300076 (253) total: 6.28s remaining: 18.4s
254: test: 0.9300083 best: 0.9300083 (254) total: 6.32s remaining: 18.5s
255: test: 0.9300140 best: 0.9300140 (255) total: 6.36s remaining: 18.5s
256: test: 0.9301413 best: 0.9301413 (256) total: 6.4s remaining: 18.5s
257: test: 0.9301032 best: 0.9301413 (256) total: 6.42s remaining: 18.5s
258: test: 0.9301285 best: 0.9301413 (256) total: 6.43s remaining: 18.4s
259: test: 0.9301203 best: 0.9301413 (256) total: 6.45s remaining: 18.4s
260: test: 0.9301233 best: 0.9301413 (256) total: 6.47s remaining: 18.3s
261: test: 0.9302612 best: 0.9302612 (261) total: 6.48s remaining: 18.3s
262: test: 0.9302735 best: 0.9302735 (262) total: 6.5s remaining: 18.2s
263: test: 0.9302782 best: 0.9302782 (263) total: 6.52s remaining: 18.2s
264: test: 0.9302833 best: 0.9302833 (264) total: 6.54s remaining: 18.1s
265: test: 0.9302857 best: 0.9302857 (265) total: 6.56s remaining: 18.1s
266: test: 0.9302820 best: 0.9302857 (265) total: 6.58s remaining: 18.1s
267: test: 0.9302913 best: 0.9302913 (267) total: 6.59s remaining: 18s
268: test: 0.9303043 best: 0.9303043 (268) total: 6.61s remaining: 18s
269: test: 0.9303183 best: 0.9303183 (269) total: 6.63s remaining: 17.9s
270: test: 0.9303087 best: 0.9303183 (269) total: 6.65s remaining: 17.9s
271: test: 0.9303068 best: 0.9303183 (269) total: 6.66s remaining: 17.8s
272: test: 0.9302882 best: 0.9303183 (269) total: 6.68s remaining: 17.8s
273: test: 0.9302828 best: 0.9303183 (269) total: 6.7s remaining: 17.8s
274: test: 0.9302918 best: 0.9303183 (269) total: 6.72s remaining: 17.7s
275: test: 0.9303092 best: 0.9303183 (269) total: 6.74s remaining: 17.7s
276: test: 0.9303167 best: 0.9303183 (269) total: 6.75s remaining: 17.6s
277: test: 0.9303371 best: 0.9303371 (277) total: 6.78s remaining: 17.6s
278: test: 0.9303319 best: 0.9303371 (277) total: 6.79s remaining: 17.6s
279: test: 0.9303030 best: 0.9303371 (277) total: 6.81s remaining: 17.5s
280: test: 0.9303527 best: 0.9303527 (280) total: 6.83s remaining: 17.5s
281: test: 0.9303598 best: 0.9303598 (281) total: 6.84s remaining: 17.4s
282: test: 0.9303746 best: 0.9303746 (282) total: 6.86s remaining: 17.4s
283: test: 0.9303657 best: 0.9303746 (282) total: 6.87s remaining: 17.3s
284: test: 0.9303958 best: 0.9303958 (284) total: 6.89s remaining: 17.3s
285: test: 0.9303845 best: 0.9303958 (284) total: 6.91s remaining: 17.3s
286: test: 0.9303872 best: 0.9303958 (284) total: 6.94s remaining: 17.2s
287: test: 0.9303851 best: 0.9303958 (284) total: 6.97s remaining: 17.2s
288: test: 0.9303922 best: 0.9303958 (284) total: 7s remaining: 17.2s
289: test: 0.9303933 best: 0.9303958 (284) total: 7.02s remaining: 17.2s
290: test: 0.9304038 best: 0.9304038 (290) total: 7.04s remaining: 17.2s
291: test: 0.9304021 best: 0.9304038 (290) total: 7.08s remaining: 17.2s
292: test: 0.9303848 best: 0.9304038 (290) total: 7.12s remaining: 17.2s
293: test: 0.9303834 best: 0.9304038 (290) total: 7.14s remaining: 17.1s
294: test: 0.9304111 best: 0.9304111 (294) total: 7.18s remaining: 17.2s
295: test: 0.9304101 best: 0.9304111 (294) total: 7.22s remaining: 17.2s
296: test: 0.9303827 best: 0.9304111 (294) total: 7.26s remaining: 17.2s
297: test: 0.9305549 best: 0.9305549 (297) total: 7.29s remaining: 17.2s
298: test: 0.9305564 best: 0.9305564 (298) total: 7.33s remaining: 17.2s
299: test: 0.9305595 best: 0.9305595 (299) total: 7.38s remaining: 17.2s
300: test: 0.9305601 best: 0.9305601 (300) total: 7.43s remaining: 17.3s
301: test: 0.9305846 best: 0.9305846 (301) total: 7.47s remaining: 17.3s
302: test: 0.9306048 best: 0.9306048 (302) total: 7.51s remaining: 17.3s
303: test: 0.9306070 best: 0.9306070 (303) total: 7.54s remaining: 17.3s
304: test: 0.9306229 best: 0.9306229 (304) total: 7.57s remaining: 17.3s
305: test: 0.9306169 best: 0.9306229 (304) total: 7.61s remaining: 17.3s
306: test: 0.9306091 best: 0.9306229 (304) total: 7.63s remaining: 17.2s
307: test: 0.9306092 best: 0.9306229 (304) total: 7.65s remaining: 17.2s
308: test: 0.9306791 best: 0.9306791 (308) total: 7.67s remaining: 17.2s
309: test: 0.9306902 best: 0.9306902 (309) total: 7.71s remaining: 17.1s
310: test: 0.9306854 best: 0.9306902 (309) total: 7.73s remaining: 17.1s
311: test: 0.9306963 best: 0.9306963 (311) total: 7.77s remaining: 17.1s
312: test: 0.9306845 best: 0.9306963 (311) total: 7.8s remaining: 17.1s
313: test: 0.9306829 best: 0.9306963 (311) total: 7.84s remaining: 17.1s
314: test: 0.9307236 best: 0.9307236 (314) total: 7.87s remaining: 17.1s
315: test: 0.9307175 best: 0.9307236 (314) total: 7.9s remaining: 17.1s
316: test: 0.9307335 best: 0.9307335 (316) total: 7.94s remaining: 17.1s
317: test: 0.9307780 best: 0.9307780 (317) total: 7.97s remaining: 17.1s
318: test: 0.9307605 best: 0.9307780 (317) total: 8.02s remaining: 17.1s
319: test: 0.9307615 best: 0.9307780 (317) total: 8.07s remaining: 17.1s
320: test: 0.9307303 best: 0.9307780 (317) total: 8.1s remaining: 17.1s
321: test: 0.9307196 best: 0.9307780 (317) total: 8.15s remaining: 17.2s
322: test: 0.9306983 best: 0.9307780 (317) total: 8.19s remaining: 17.2s
323: test: 0.9307008 best: 0.9307780 (317) total: 8.23s remaining: 17.2s
324: test: 0.9307045 best: 0.9307780 (317) total: 8.27s remaining: 17.2s
325: test: 0.9307154 best: 0.9307780 (317) total: 8.3s remaining: 17.2s
326: test: 0.9307355 best: 0.9307780 (317) total: 8.33s remaining: 17.1s
327: test: 0.9307408 best: 0.9307780 (317) total: 8.35s remaining: 17.1s
328: test: 0.9307221 best: 0.9307780 (317) total: 8.37s remaining: 17.1s
329: test: 0.9307166 best: 0.9307780 (317) total: 8.39s remaining: 17s
330: test: 0.9307131 best: 0.9307780 (317) total: 8.41s remaining: 17s
331: test: 0.9307283 best: 0.9307780 (317) total: 8.43s remaining: 17s
332: test: 0.9307275 best: 0.9307780 (317) total: 8.45s remaining: 16.9s
333: test: 0.9307365 best: 0.9307780 (317) total: 8.47s remaining: 16.9s
334: test: 0.9307500 best: 0.9307780 (317) total: 8.51s remaining: 16.9s
335: test: 0.9307699 best: 0.9307780 (317) total: 8.54s remaining: 16.9s
336: test: 0.9307739 best: 0.9307780 (317) total: 8.56s remaining: 16.9s
337: test: 0.9307418 best: 0.9307780 (317) total: 8.6s remaining: 16.8s
Stopped by overfitting detector (20 iterations wait)

bestTest = 0.930778032
bestIteration = 317

Shrink model to first 318 iterations.

Out[1020]:

<catboost.core.CatBoostClassifier at 0x7f7d45807610>

Соберем пайплайн целиком

In [1021]:

# pipeline = Pipeline([("preprocess", preprocessor), ("model", rf)])
# pipeline

И запустим обучение

In [1022]:

# pipeline.fit(X_train, y_train)
# pipeline

Оценка качества модели¶

Получим предсказания на тесте обученной модели

In [1023]:

# y_proba = pipeline.predict_proba(X_test)[:, 1]
y_proba = cb.predict_proba(X_test)[:, 1]

In [1024]:

y_proba.shape

Out[1024]:

(9769,)

In [1025]:

y_pred = np.where(y_proba >= 0.5, 1, 0)

Считаем метрики

In [1026]:

accuracy = accuracy_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)
roc_auc = roc_auc_score(y_test, y_proba)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)

prec, rec, thresholds = precision_recall_curve(y_test, y_proba)
pr_auc = auc(rec, prec)

In [1027]:

print(f"Accuracy: {accuracy:.4f}")
print(f"F1-score: {f1:.4f}")
print(f"ROC-AUC: {roc_auc:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall: {recall:.4f}")
print(f"PR-AUC: {pr_auc:.4f}")

Accuracy: 0.8762
F1-score: 0.7149
ROC-AUC: 0.9308
Precision: 0.7975
Recall: 0.6479
PR-AUC: 0.8323

In [1028]:

fig = plt.figure(figsize=(8, 6))

plt.plot(rec, prec)

plt.xlabel("Recall")
plt.ylabel("Precision")
plt.title("PR-Curve")
plt.legend()
plt.grid(True, alpha=0.3)

/tmp/ipykernel_1264561/1431705682.py:8: UserWarning: No artists with labels found to put in legend. Note that artists whose label start with an underscore are ignored when legend() is called with no argument.
 plt.legend()

In [1029]:

data_params = {
 "test_size": TEST_SIZE,
 "cat_encoder": pipeline.get_params()["steps"][0][1].get_params()["transformers"][0][1].__class__.__name__,
 "num_encoder": pipeline.get_params()["steps"][0][1].get_params()["transformers"][1][1].__class__.__name__,
}

input_example = X_train.iloc[[0]]

In [ ]:

with mlflow.start_run(run_name=exp_name):
 mlflow.log_metrics({"accuracy": accuracy, "f1_score": f1, "roc_auc": roc_auc, "precision": precision, "recall": recall, "pr_auc": pr_auc})
 # mlflow.log_params(dict(lr_params, **{'model_type': 'LogisticRegression'}, **data_params))
 # mlflow.log_params(dict(rf_params, **{'model_type': 'RandomForest'}, **data_params))
 mlflow.log_params(dict(cb_params, **{"model_type": "CatBoost", "test_size": TEST_SIZE}))

 mlflow.log_figure(fig, "plots/pr_curve.png")
 # mlflow.sklearn.log_model(pipeline, artifact_path="model", input_example=input_example)
 mlflow.catboost.log_model(cb, artifact_path="model", input_example=input_example)

plt.close(fig)
