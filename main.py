from __future__ import division
from math import sqrt
import sys
import urllib.request
import time
import re
import statsmodels.formula.api as smf
from PyQt4 import QtCore, QtGui, QtSql
from PyQt4.QtCore import QUrl,pyqtSlot,SIGNAL,SLOT
from PyQt4.QtSql import QSqlQueryModel 
from PyQt4.QtGui import QMessageBox,QSound
import scipy
import sqlite3
import calendar
from apscheduler.schedulers.qt import QtScheduler
from apscheduler.executors.pool import ProcessPoolExecutor
from datetime import datetime
import pandas as pd
import h2o
from h2o.estimators import H2ODeepLearningEstimator
import numpy as np
import paho.mqtt.client as mqtt
import json

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s
from matplotlib.backends.backend_qt4agg import (
    FigureCanvasQTAgg as FigureCanvas)
    
import seaborn as sns
sns.set(color_codes=True)

import serm

import skfuzzy as fuzz
from skfuzzy import control as ctrl

FFWI = ctrl.Antecedent(np.arange(0, 110, 5), 'FFWI')
SMOKE = ctrl.Antecedent(np.arange(0, 1100, 100), 'SMOKE')
RISK = ctrl.Consequent(np.arange(0, 110, 10), 'RISK')

FFWI['low'] = fuzz.trimf(FFWI.universe, [0, 0, 25])
FFWI['moderate'] = fuzz.trimf(FFWI.universe, [0, 25, 50])
FFWI['high'] = fuzz.trimf(FFWI.universe, [25, 50, 75])
FFWI['very high'] = fuzz.trimf(FFWI.universe, [50, 75, 100])
FFWI['extreme'] = fuzz.trimf(FFWI.universe, [75, 100, 100])

SMOKE['low'] = fuzz.trimf(SMOKE.universe, [0, 0, 500])
SMOKE['average'] = fuzz.trimf(SMOKE.universe, [0, 500, 1000])
SMOKE['high'] = fuzz.trimf(SMOKE.universe, [500, 1000, 1000])

RISK['low'] = fuzz.trimf(RISK.universe, [0, 0, 50])
RISK['average'] = fuzz.trimf(RISK.universe, [0, 50, 100])
RISK['high'] = fuzz.trimf(RISK.universe, [50, 100, 100])

rule1 = ctrl.Rule(FFWI['low'] & SMOKE['low'], RISK['low'])
rule2 = ctrl.Rule(FFWI['moderate'] & SMOKE['low'], RISK['low'])
rule3 = ctrl.Rule(FFWI['high'] & SMOKE['low'], RISK['average'])
rule4 = ctrl.Rule(FFWI['high'] & SMOKE['low'], RISK['average'])
rule5 = ctrl.Rule(SMOKE['average'], RISK['average'])
rule6 = ctrl.Rule(FFWI['very high'], RISK['high'])
rule7 = ctrl.Rule(SMOKE['high'] | FFWI['extreme'], RISK['high'])

risk_ctrl = ctrl.ControlSystem([rule1, rule2, rule3, rule4, rule5, rule6, rule7])

predict_risk = ctrl.ControlSystemSimulation(risk_ctrl)

client = mqtt.Client(client_id="MQTTrec", clean_session=True, protocol=mqtt.MQTTv31)

executors = {
    'default': {'type': 'threadpool', 'max_workers': 1},
    'processpool': ProcessPoolExecutor(max_workers=1)
    }
job_defaults = {
    'coalesce': True,
    'max_instances': 5
    }   
        
scheduler  = QtScheduler(executors=executors, job_defaults=job_defaults)

def initdatabases():

    conn = sqlite3.connect('serm.db')

    with conn:

        conn.execute("DROP TABLE IF EXISTS data")

        conn.execute('''CREATE TABLE data
           (
           recid            INTEGER  PRIMARY KEY AUTOINCREMENT,
           datetime         INTEGER  NOT NULL,
           smoke            float    NOT NULL,
           lpg              float    NOT NULL,
           co               float    NOT NULL,
           temperature      float    NOT NULL,
           humidity         float    NOT NULL,
           windspeed        float    NOT NULL,
           winddir          varchar(3)     NOT NULL,
           ffwi             float    NOT NULL);''')
        
        datetm = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    
        conn.execute("INSERT INTO data(datetime,smoke,lpg,co,temperature,humidity,windspeed,winddir,ffwi) VALUES (?,?,?,?,?,?,?,?,?)", (datetm,0,0,0,0,0,0,0,0))
    
        conn.commit()
            
    with conn:

        conn.execute("DROP TABLE IF EXISTS predictions")

        conn.execute('''CREATE TABLE predictions
           (
           recid            INTEGER  PRIMARY KEY AUTOINCREMENT,
           datetime         INTEGER  NULL,
           smoke            float    NULL,
           temperature      float    NULL,
           humidity         float    NULL,
           windspeed        float    NULL,
           fri              float    NULL,
           ffwi             float    NULL);''')
        
        datetm = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    
    
        conn.execute("INSERT INTO predictions(datetime,smoke,temperature,humidity,windspeed,fri,ffwi) VALUES (?,?,?,?,?,?,?)", (datetm,0,0,0,0,0,0))
    
        conn.commit()
                    
    with conn:

        conn.execute("DROP TABLE IF EXISTS data_means")

        conn.execute('''CREATE TABLE data_means
           (
           recid            INTEGER  PRIMARY KEY AUTOINCREMENT,
           timestamp        INTEGER  NOT NULL,
           datetime         text     NOT NULL,
           smoke            float    NOT NULL,
           lpg              float    NOT NULL,
           co               float    NOT NULL,
           temperature      float    NOT NULL,
           humidity         float    NOT NULL,
           windspeed        float    NOT NULL,
           winddir          varchar(3)     NOT NULL,
           ffwi             float    NOT NULL,
           risk             float    NOT NULL);''')
        
        datetm = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
    
        conn.execute("INSERT INTO data_means(timestamp,datetime,smoke,lpg,co,temperature,humidity,windspeed,winddir,ffwi,risk) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (0,datetm,0,0,0,0,0,0,0,0,0))
    
        conn.commit()
                
    conn.close()

global weather
global weather_df
global train
global test
global valid
global model

class MyWindowClass(QtGui.QMainWindow,serm.Ui_MainWindow):
    def __init__(self, parent=None):
        QtGui.QMainWindow.__init__(self, parent)
        self.ui = serm.Ui_MainWindow()
        self.setupUi(self)
        self.pushButton_predict_risk.clicked.connect(self.predict_risk)
        self.pushButton_DA_showplot.clicked.connect(self.showplot)
        self.pushButton_DA_pearson.clicked.connect(self.calc_consist)
        self.pushButton_PM_H2Oinit.clicked.connect(self.h2oinitfunc)
        self.pushButton_DA_data_consist.clicked.connect(self.data_integrity_check)
        self.pushButton_PM_Predict.clicked.connect(self.model_predict)
        self.pushButton_PM_FWI.clicked.connect(self.calc_FWI)
        self.pushButton_PM_BuildModel.clicked.connect(self.H2OBuildModel)
        self.pushButton_PM_LastWData.clicked.connect(self.h2ogetdata)
        self.pushButton_PM_addRecord.clicked.connect(self.addrow)
        self.pushButton_PM_addweatherRecord.clicked.connect(self.addweatherrow)
        self.tabMenu.connect(self.tabMenu,SIGNAL("currentChanged(int)"),self,SLOT("tabChangedSlot(int)"))
        self.dateTimeEdit.setDateTime(datetime.now()) 
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.on_subscribe = self.on_subscribe
        #client.connect("broker.hivemq.com", 1883,keepalive=0)
        #client.connect("test.mosquitto.org",1883,keepalive=0)
        client.connect("localhost", 1883,keepalive=0)
        self.dial.valueChanged.connect(self.lbl_dialnum.setNum)
        self.fn_gphlr()
        scheduler.add_job(self.readData, 'interval', seconds=1, misfire_grace_time=2, id='readdata')
        scheduler.add_job(self.timed_job, 'interval', seconds=10, id='recmeans')
        scheduler.add_job(self.wunderground, 'interval', minutes=5, misfire_grace_time=2, id='wunderground')
        self.wunderground()        
        self.timed_job()

    model = None
    test = None
     
    def show_predictions_table(self):
        db = QtSql.QSqlDatabase.addDatabase("QSQLITE")
        self.tableView_PM.setWindowTitle("Connect to QSQLITE Database Example")                          
        db.setHostName("localhost")
        db.setDatabaseName("serm.db")
        db.setUserName("")
        db.setPassword("")

        if (db.open()==False): 
            message = "Database Error"
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText("Error at opening database")
            msg.setInformativeText(message)
            msg.setWindowTitle("Informative Message")
            msg.setStandardButtons(QMessageBox.Close)
            msg.exec_()               
        
        projectModel = QSqlQueryModel()
        projectModel.setQuery("SELECT datetime,smoke,temperature,humidity,windspeed,fri,ffwi FROM predictions ORDER BY recid DESC",db)
        
        self.tableView_PM.setModel(projectModel)
        self.tableView_PM.adjustSize
        self.tableView_PM.setColumnWidth(0,160)
        self.tableView_PM.show()  
        
    def addrow(self):

        conn = sqlite3.connect('serm.db')

        with conn:
            dtm = self.dateTimeEdit_PM_datetime.text()
            smk = self.doubleSpinBox_PM_smoke.text()
            tmp = self.doubleSpinBox_PM_temp.text()
            hmd = self.doubleSpinBox_PM_humidity.text()
            wndspd = self.doubleSpinBox_PM_WindSpeed.text()
            ffwi = self.lineEdit_PM_calcFWI.text()
            risk = self.lineEdit_PM_predictRiskVal.text()          
            conn.execute("INSERT INTO predictions(datetime,smoke,temperature,humidity,windspeed,fri,ffwi) VALUES (?,?,?,?,?,?,?)", (dtm,smk,tmp,hmd,wndspd,risk,ffwi))
        conn.close()
        self.show_predictions_table()
        
    def addweatherrow(self):

        conn = sqlite3.connect('serm.db')

        with conn:
            dt = self.dateTimeEdit_PM_datetime.dateTime()
            dtm = datetime.strftime(dt.toPyDateTime(), '%Y-%m-%d %H:%M:%S')
            smk = self.doubleSpinBox_PM_smoke.value()
            print(smk)
            tmp = self.doubleSpinBox_PM_temp.value()
            hmd = self.doubleSpinBox_PM_humidity.value()
            wndspd = self.doubleSpinBox_PM_WindSpeed.value()
            ffwi = self.lineEdit_PM_calcFWI.text()
            risk = self.lineEdit_PM_predictRiskVal.text()
            ddate = self.dateTimeEdit_PM_datetime.dateTime()
            date_var = ddate.toPyDateTime()
            tstmp = time.mktime(date_var.timetuple())
            conn.execute("INSERT INTO data_means(timestamp,datetime,smoke,co,lpg,temperature,humidity,windspeed,winddir,risk,ffwi) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (tstmp,dtm,smk,0,0,tmp,hmd,wndspd,'X',risk,ffwi))
        conn.close()
        self.show_predictions_table()

    def on_connect(self,client, userdata, flags, rc):
        print("CONNACK received with code %d." % (rc))
        client.subscribe("/SERM",0)

    def on_message(self,client, userdata, msg):
        if msg.payload:   
            self.dateTimeEdit.setDateTime(datetime.now())  
            data =  str(msg.payload).strip("b,',\n,\\")
            parsed_json = json.loads(data)
            smk = str(parsed_json['smk'])
            lpg = str(parsed_json['lpg'])
            co = str(parsed_json['co'])
            hum = str(parsed_json['hum'])
            temp = str(parsed_json['temp'])
            wndspd = str(parsed_json['wndspd'])
            wnddir = (parsed_json['wnddir'])
            datetimestamp = calendar.timegm(time.strptime(str(time.strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S'))
                
            T = float(temp)
            H = float(float(hum)/100)
            W = 349 + (1.29*T)+(0.0135*(T**2))
            K = 0.805 + 0.000736*T - 0.000000273*(T**2)
            K1 = 6.27 + 0.000938*T - 0.0000303*(T**2)
            K2 = 1.91 + 0.0407*T - 0.000293*(T**2)
            M = 1800/W *(((K*H)/(1-(K*H)))+(((K1*K*H)+(2*K1*K2*(K**2)*(H**2)))/(1+(K1*K*H)+(K1*K2*(K**2)*(H**2)))))
        
            WMPH = float(wndspd)
        
            M30 = M/30
            WSQR = WMPH*WMPH
            fmdc = 1 - 2*M30 + 1.5*M30**2 - 0.5*M30**3
            CMBE = (fmdc*sqrt(1+WSQR))/0.3002
        
            conn = sqlite3.connect('serm.db')
            with conn:
                conn.execute("INSERT INTO data(datetime,smoke,lpg,co,humidity,temperature,windspeed,winddir,ffwi) VALUES (?,?,?,?,?,?,?,?,?)", (datetimestamp,smk,lpg,co,hum,temp,wndspd,wnddir,str(CMBE)))    
                conn.commit()
            
                
    def on_subscribe(self,client, userdata, mid, granted_qos):
        print("Subscribed: "+str(mid)+" "+str(granted_qos))

    def on_log(self,client, obj, level, string):
        print(string)
        
    @pyqtSlot(int)
    def tabChangedSlot(self,argTabIndex):
        
        if argTabIndex==1:
            db = QtSql.QSqlDatabase.addDatabase("QSQLITE")
            self.tableView.setWindowTitle("Connect to QSQLITE Database Example")                          
            db.setHostName("localhost")
            db.setDatabaseName("serm_shadow.db")
            db.setUserName("")
            db.setPassword("")
                        
            if (db.open()==False): 
                message = "Database Error"
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Error at opening database")
                msg.setInformativeText(message)
                msg.setWindowTitle("Informative Message")
                msg.setStandardButtons(QMessageBox.Close)
                msg.exec_()  
                
            projectModel = QSqlQueryModel()
            projectModel.setQuery("SELECT datetime,temperature,humidity,smoke,lpg,co,windspeed,winddir,ffwi,risk FROM data_means ORDER BY recid DESC",db)
            self.tableView.setModel(projectModel)
            self.tableView.adjustSize
            self.tableView.setColumnWidth(0,168)
            self.tableView.show()
            
        elif argTabIndex==3:      
            conn = sqlite3.connect('serm.db')                 
            ds = pd.read_sql("SELECT timestamp,datetime,risk,smoke,temperature,humidity,windspeed,ffwi from data_means", conn);
            conn.close()
            ds.to_csv("serm.csv")
            self.show_predictions_table()
            
    def fn_gphlr(self):
        conn = sqlite3.connect('serm.db')                 
        ds = pd.read_sql("SELECT timestamp,recid,ffwi,risk,smoke from data_means", conn);
        dx = ds.recid
        dy = ds.risk
        pl2 = sns.regplot(dx,dy,data=dy,order=2)      
        fig2 = pl2.figure
        self.addmpl(fig2)

    def showplot(self):
        conn = sqlite3.connect('serm_shadow.db')                 
        df = pd.read_sql("SELECT ffwi,temperature,smoke,humidity,windspeed from data_means", conn)
        self.gridLayout_DA_plot.removeWidget(self.canvas)
        if self.comboBox_DA_diag.currentText() == "Histogram":
            g = sns.pairplot(df,dropna=True,diag_kind="hist",size=2.2)
        fig = g.fig
        self.canvas = FigureCanvas(fig)
        self.gridLayout_DA_plot.addWidget(self.canvas)
        self.canvas.draw()

    def calc_FWI(self):
        humidity = self.doubleSpinBox_PM_humidity.value()
        temperature = self.doubleSpinBox_PM_temp.value()
        windspeed = self.doubleSpinBox_PM_WindSpeed.value()
        ###############################################################################################
        T = float(temperature)
        H = float(float(humidity)/100)
        W = 349 + (1.29*T)+(0.0135*(T**2))
        K = 0.805 + 0.000736*T - 0.000000273*(T**2)
        K1 = 6.27 + 0.000938*T - 0.0000303*(T**2)
        K2 = 1.91 + 0.0407*T - 0.000293*(T**2)
        M = 1800/W *(((K*H)/(1-(K*H)))+(((K1*K*H)+(2*K1*K2*(K**2)*(H**2)))/(1+(K1*K*H)+(K1*K2*(K**2)*(H**2)))))
        
        WMPH = float(windspeed)
        
        M30 = M/30
        WSQR = WMPH*WMPH
        fmdc = 1 - 2*M30 + 1.5*M30**2 - 0.5*M30**3
        CMBE = (fmdc*sqrt(1+WSQR))/0.3002
        ###############################################################################################
        ffwi = str(round(CMBE,3))          
        self.lineEdit_PM_calcFWI.setText(ffwi)
            
    def model_predict(self):
        global model
        global test
        datevar = self.dateTimeEdit_PM_datetime.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        ffwi = self.lineEdit_PM_calcFWI.text()
        smoke = self.doubleSpinBox_PM_smoke.value()
        humidity = self.doubleSpinBox_PM_humidity.value()
        temperature = self.doubleSpinBox_PM_temp.value()
        windspeed = self.doubleSpinBox_PM_WindSpeed.value()    
        d = [datevar, ffwi, smoke , temperature, humidity, windspeed]
        f = h2o.H2OFrame(d) 
        f.set_names(["datetime","ffwi","smoke","temperature", "humidity", "windspeed"])
        predict = model.predict(f)
        fnum = re.findall("[-+]?[0-9]*\.?[0-9]+", str(predict))
        self.lineEdit_PM_predictRiskVal.setText(fnum[0])
        
    def data_integrity_check(self):
        conn = sqlite3.connect('serm_shadow.db')  
        message = None
        data = pd.read_sql("SELECT risk,temperature,smoke,humidity,windspeed from data_means", conn)
        assert(0 < len(data))
        for index, row in data.iterrows():
            assert(row["smoke"] >= 0),message + "Undefined Smoke value(s)\n"
            assert(row["windspeed"] >= 0),message +"Undefined Windspeed value(s)\n"
            assert(row["risk"] >= 0),message + "Undefined Risk value(s)\n"
            assert(row["humidity"] >= 0),message + "Undefined Humidity value(s)\n"
        if message == None:
            message = "No errors on data"
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText("Data consisteny completed successfully")
        msg.setInformativeText(message)
        msg.setWindowTitle("MessageBox")
        msg.setStandardButtons(QMessageBox.Close)
        msg.exec_()

    def calc_consist(self):
        var1 = "risk"
        var2 = None
        if self.radioButton_PM_FWI.isChecked()==True :
            var2 = "ffwi"

        if self.radioButton_PM_TMP.isChecked()==True :
            var2 = "temperature"  
            
        if self.radioButton_PM_HM.isChecked()==True :
            var2 = "humidity"

        if self.radioButton_PM_WNSPD.isChecked()==True :
            var2 = "windspeed"  
            
        if self.radioButton_PM_SMK.isChecked()==True :
            var2 = "smoke"  

        conn = sqlite3.connect('serm_shadow.db')                 
        data = pd.read_sql("SELECT risk,ffwi,temperature,smoke,humidity,windspeed from data_means", conn)

        if self.radioButton_DA_pears.isChecked() == True:        
            r_row, p_value = scipy.stats.pearsonr(data[var1], data[var2])
        elif self.radioButton_DA_spear.isChecked() == True:
            r_row, p_value = scipy.stats.spearmanr(data[var1], data[var2])
            
        self.lineEdit_DA_coefficient.setText(str(round(r_row,3)));
        self.lineEdit_DA_pvalue.setText(str(round(p_value,3)));

    def removeplot(self):
        self.gridLayout_DA_plot.removeWidget(self.canvas)
        self.canvas.close()

    def H2OBuildModel(self):
        weather = "serm.csv"
        weather_df = h2o.import_file(path=weather)   
        global model
        global test
        train,test,valid = weather_df.split_frame(ratios=(.7, .15))

        estimator_index = self.tabWidget_PM_Estimator.currentIndex()
        
        if estimator_index == 0:
            _distribution = self.comboBox_PM_distribution.currentText()
            _activation = self.comboBox_PM_activation.currentText()
            _hidden = self.comboBox_PM_hidden.currentText()
            _epochs = self.spinBox_PM_epochs.value()
            _sparse = self.comboBox_PM_sparse.currentText()
            _shuffle = self.comboBox_PM_shuffle.currentText()
            model = H2ODeepLearningEstimator(distribution=_distribution,activation=_activation,hidden=_hidden,shuffle = _shuffle,sparse=_sparse,epochs=_epochs)
                
        self.completed = 0

        while self.completed < 100:
            self.completed += 0.0001
            self.progressBar.setValue(self.completed)
            
        model.train(y="risk", x=["datetime","ffwi","smoke","temperature", "humidity", "windspeed"], training_frame=train)
        metrics = model.model_performance()
        self.lineEdit_PM_MSE.setText(str(round(metrics['MSE'],5)))
        self.lineEdit_PM_RMSE.setText(str(round(metrics['RMSE'],5)))
        self.lineEdit_PM_MAE.setText(str(round(metrics['mae'],5)))
        self.lineEdit_PM_MRD.setText(str(round(metrics['mean_residual_deviance'],5)))
                
        
    def predict_risk(self):
        selected_hours = int(self.lbl_dialnum.text())
        conn = sqlite3.connect('serm.db')

        with conn:        
        
            df = pd.read_sql("SELECT recid,risk from data_means", conn);
            lm = smf.ols("risk ~ recid", data=df).fit()            
            cur = conn.cursor()    
            cur.execute('SELECT MAX(recid) from data_means')
            data = cur.fetchone()
            c_recid = data[0]
            
        counts = int((selected_hours * 60)*60)
        
        total = counts+c_recid
        idx = []
        riskarr = []
        for x in range(c_recid, total):
            riskarr.append(lm.predict({'recid': x}))
            idx.append(x)
        df = pd.DataFrame(riskarr, index=idx)

        self.txt_mean.setText(str(round(df.mean()[0],3)))
        self.txt_max.setText(str(round(df.max()[0],3)))
        self.txt_min.setText(str(round(df.min()[0],3)))
                
        palette = QtGui.QPalette()
        risk = df.mean()[0]

        if risk < 10:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.green)
            self.txt_max_2.setPalette(palette)
            self.txt_max_2.setText("LOW")
        elif risk >= 10 and risk < 30:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.yellow)
            self.txt_max_2.setPalette(palette)
            self.txt_max_2.setText("AVERAGE")
        else:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.red)
            self.txt_max_2.setPalette(palette)
            self.txt_max_2.setText("HIGH")
            

    def readData(self):
        client.loop()

    def h2ogetdata(self):
        weather = "serm.csv"
        weather_df = h2o.import_file(path=weather)   
        self.doubleSpinBox_PM_temp.setValue(weather_df.tail(1)['temperature'])
        self.doubleSpinBox_PM_humidity.setValue(weather_df.tail(1)['humidity'])
        self.doubleSpinBox_PM_smoke.setValue(weather_df.tail(1)['smoke'])
        self.doubleSpinBox_PM_WindSpeed.setValue(weather_df.tail(1)['windspeed'])
        #strfwi = re.findall("[-+]?[0-9]*\.?[0-9]+", str(weather_df.tail(1)['ffwi']))
        #self.lineEdit_PM_calcFWI.setText(strfwi[0])
        dttmstamp = datetime.utcfromtimestamp(weather_df.tail(1)['timestamp'])
        self.dateTimeEdit_PM_datetime.setDateTime(dttmstamp)
        
    def h2oinitfunc(self):
        h2o.init()
        if str(h2o.connection())=="<H2OConnection to http://localhost:54321, no session>":
            self.lineEdit_PM_h2o_response.setText("Connection to H2O cluster Successful")
        else:
            self.lineEdit_PM_h2o_response.setText("Connection to H2O cluster Failed")            
        
    def timed_job(self):

        conn = sqlite3.connect('serm.db')

        with conn:
            
            df = pd.read_sql_query("SELECT * from data", conn);
            df.humidity = np.array(df.humidity.astype(float))
            df.temperature = np.array(df.temperature.astype(float))
            df.smoke = np.array(df.smoke.astype(float))
            df.co = np.array(df.co.astype(float))
            df.lpg = np.array(df.lpg.astype(float))
            df.windspeed = np.array(df.windspeed.astype(float)) 
            df.ffwi = np.array(df.ffwi.astype(float))                    
            datetm = calendar.timegm(time.strptime(str(time.strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S'))
            datedt = time.strftime('%Y-%m-%d %H:%M:%S')
            winddir = df.winddir.tail(1).iget(0)

            predict_risk.input['FFWI'] = df.ffwi.mean()
            predict_risk.input['SMOKE'] = df.smoke.mean()
            predict_risk.compute()
            
            risk = predict_risk.output['RISK']
            
            conn.execute("INSERT INTO data_means(timestamp,datetime,smoke,lpg,co,temperature,humidity,windspeed,winddir,ffwi,risk) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (datetm,datedt,round(df.smoke.mean(),3),round(df.lpg.mean(),3),round(df.co.mean(),3),round(df.temperature.mean(),3),round(df.humidity.mean(),3),round(df.windspeed.mean(),3),winddir,round(df.ffwi.mean(),3),round(risk,3)))
            conn.commit()
            
            sql = "DELETE FROM data WHERE recid <= ( SELECT recid FROM (SELECT recid FROM data ORDER BY recid DESC LIMIT 1 OFFSET 20)foo)"
            conn.execute(sql)
            conn.commit()

#        self.lcdNumber_ffwi.display(str(round(df.ffwi.mean(),-1)))           
        self.lcdNumber_ffwi.display(str(df.ffwi.mean()))
        self.lcdNumber_risk.display((risk))
        
        palette = QtGui.QPalette()

        if risk < 10:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.green)
            self.lbl_RiskStateValue.setPalette(palette)
            self.lbl_RiskStateValue.setText("LOW")
        elif risk >= 10 and risk < 30:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.yellow)
            self.lbl_RiskStateValue.setPalette(palette)
            self.lbl_RiskStateValue.setText("AVERAGE")
        else:
            palette.setColor(QtGui.QPalette.Foreground,QtCore.Qt.red)
            self.lbl_RiskStateValue.setPalette(palette)
            self.lbl_RiskStateValue.setText("HIGH")
            sound = QSound("smoke-detector-1.wav")
            sound.play() 
                    
    def setclock(self,):
        self.dateTimeEdit.setDateTime(datetime.now())  

    def rmmpl(self,):
        self.gridLayout.removeWidget(self.canvas)
        self.canvas.close()
            
    def addmpl(self,fig):
        self.canvas = FigureCanvas(fig)
        self.gridLayout.addWidget(self.canvas)
        self.canvas.draw()
        
    def wunderground(self):
        webURL = urllib.request.urlopen('http://api.wunderground.com/api/3efe05c687cbcdcb/geolookup/conditions/q/GR/Tripolis.json')
        json_string = webURL.read()
        encoding = webURL.info().get_content_charset('utf-8')
        parsed_json = json.loads(json_string.decode(encoding))
        temp_f = parsed_json['current_observation']['temp_c']
        relative_humidity = parsed_json['current_observation']['relative_humidity']
        wind_dir = parsed_json['current_observation']['wind_dir']
        wind_kph = parsed_json['current_observation']['wind_kph']
        self.ln_ctmp.setText(str(temp_f))
        self.ln_relh.setText(str(relative_humidity))
        self.ln_wndsp.setText(str(wind_kph))
        self.ln_wnd.setText(str(wind_dir))
        webURL.close()

if __name__ == "__main__": 
       
    print ("Operation started")
    
    #initdatabases()
     
    app = QtGui.QApplication(sys.argv)
    
    myWindow = MyWindowClass()
       
    myWindow.webView.load(QUrl('http://localhost/attendance/livedata')) 
            
    scheduler.start() 
    
    myWindow.showMaximized()
    
    sys.exit(app.exec_())
