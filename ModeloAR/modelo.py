# from matplotlib import pyplot
from statsmodels.tsa.ar_model import AutoReg, ar_select_order
from statsmodels.tsa.api import acf, pacf, graphics
from sklearn.metrics import mean_squared_error
from math import sqrt
import numpy as np
# import sys
# import os
# sys.path.append(os.path.realpath('.'))
import pandas as pd
from scipy.spatial import distance
import scipy as stats
from matplotlib import pyplot
from statsmodels.tsa.ar_model import AutoReg, ar_select_order
from statsmodels.tsa.api import acf, pacf, graphics
from sklearn.metrics import mean_squared_error
from datetime import datetime
from math import sqrt
from .peaks import scpa
from .data import getDataDay, getParquetDay
from models import *
from sqlalchemy import func

def extraer_coef_total(data):   #Por sensor
    model = []
    for i in range(24):
        for j in range(3):
            model.append(AutoReg(data[i][j], lags = [1,2,3,4,5,6], old_names=True))
    model_fit = []
    for i in range(24*3):
        model_fit.append(model[i].fit())
    coef = []
    coef.append([x.params for x in model_fit])
    print(coef)
    return coef


def mahalanobis(x=None, data=None, cov=None): # (xi - x_mean)^T * cov^-1 * (xi - x_mean)
    x_mu = x - np.mean(data) # xi - x_mean
    if not cov:
        cov = np.cov(data.values.T)
    inv_covmat = np.linalg.inv(cov) # cov^-1
    left = np.dot(x_mu, inv_covmat) # (xi - x_mean)^T * cov^-1
    mahal = np.dot(left, x_mu.T) # (xi - x_mean)^T * cov^-1 * (xi - x_mean)
    #print(mahal)
    return mahal.diagonal()

def mahalanobisScipy(x=None, data=None, cov=None): # (xi - x_mean)^T * cov^-1 * (xi - x_mean)
    mahal = []
    x_mean = np.mean(data) # xi - x_mean
    #print(x.loc[0])
    if not cov:
        cov = np.cov(data.values.T)
    inv_covmat = np.linalg.inv(cov)
    for i in range(len(x)):
        dist = distance.mahalanobis(x.loc[i],x_mean,inv_covmat)
        mahal.append(dist*dist)
    return list(mahal)

def aplicar_modelo_total():
    for hora in range(24):
        print("Hora = ", hora)
        aplicar_modelo(hora)


def applyCoef(serie):
    model = []
    for i in range(3):
        model.append(AutoReg(serie[i], lags = [1,2,3,4,5,6], old_names=True))
    model_fit = []
    for i in range(3):
        model_fit.append(model[i].fit())
    coef = [x.params for x in model_fit]
    return coef


def aplicar_modelo(hora):
    sensor = 'AC05'
    day = datetime(2021, 5, 30, 00, 00)
    date = str(day.day).zfill(2) + '_' + str(day.month).zfill(2) + '_' + str(day.year)
    data = getParquetDay(sensor, date, hora)
    time = data['timestamp']
    try:
        x = np.array(data['x'])
    except:
        x = np.array(0)
    try:
        y = np.array(data['y'])
    except:
        y = np.array(0)
    try:
        z = np.array(data['z'])
    except:
        z = np.array(0)
    if x.any(): series_x = scpa(time, x, 3, 60)
    if y.any(): series_y = scpa(time, y, 3, 60)
    if z.any(): series_z = scpa(time, z, 3, 60)
    sens_x = []
    sens_y = []
    sens_z = []
    for i in range(0,3):
        if x.any(): sens_x.append(np.array(x[series_x[i][0]:series_x[i][-1]]))
        if y.any(): sens_y.append(np.array(y[series_y[i][0]:series_y[i][-1]]))
        if z.any(): sens_z.append(np.array(z[series_z[i][0]:series_z[i][-1]]))
    if x.any(): x_coef = applyCoef(sens_x)
    if y.any(): y_coef = applyCoef(sens_y)
    if z.any(): z_coef = applyCoef(sens_z)
    # print("x coef = ", x_coef)
    # print("y coef = ", y_coef)
    # print("z coef = ", z_coef)
    if x.any(): saveCoef(time[0], sensor, x_coef, axis = 0)
    if y.any(): saveCoef(time[0], sensor, y_coef, axis = 1)
    if z.any(): saveCoef(time[0], sensor, z_coef, axis = 2)


def saveCoef(hora, sensor, data, axis = 0):  # Guarda los coeficientes en la base de datos
    try:
        sensor_instalado = DescripcionSensor.query.filter_by(descripcion = str(sensor)).first()
        sensor_id = sensor_instalado.id_sensor_instalado
        reporte = ReporteDanoAR(id_sensor_instalado = sensor_id, hora = hora, axis = axis)
        db.session.add(reporte)
        db.session.flush()
        for i,serie in enumerate(data):
            modelo = ModeloAR(id_reporte_dano_ar = reporte.id, numero_modelo = i)
            db.session.add(modelo)
            db.session.flush()
            for j, valor in enumerate(serie):
               coef = CoeficienteAR(id_modelo_ar = modelo.id, valor = valor, numero = j)
               db.session.add(coef)
        db.session.commit()
    except:
        print("Fallo consulta")
        db.session.rollback()

def getCoef(puente_id, nombre_sensor, eje):
    coeficientes = db.session.query(CoeficienteAR.valor, CoeficienteAR.numero, ModeloAR.numero_modelo, ReporteDanoAR.id.label("reporte_dano_id") ).filter(DescripcionSensor.descripcion == nombre_sensor, ReporteDanoAR.axis == eje, DescripcionSensor.id_sensor_instalado == SensorInstalado.id, SensorInstalado.id == ReporteDanoAR.id_sensor_instalado, ReporteDanoAR.id == ModeloAR.id_reporte_dano_ar, ModeloAR.id == CoeficienteAR.id_modelo_ar)
    df_coef = pd.read_sql(coeficientes.statement, db.session.bind)
    # print(df_coef.head())
    return df_coef

def deleteFirstReporteDano():
    try:
        subquery = db.session.query(func.min(ReporteDanoAR.hora)).subquery()
        query = db.session.query(ReporteDanoAR).filter(ReporteDanoAR.hora == subquery)
        count_del = 0
        for col in query:
            count_del += 1
            delete_col = db.session.query(ReporteDanoAR).filter(ReporteDanoAR.id == col.id).delete()
            db.session.commit()
        print("columnas eliminadas", count_del)
    except:
        print("Fallo consulta")
        db.session.rollback()
    return

def getDamage(puente_id, nombre_sensor):
    flag_damage = False
    for eje in range(3):
        df = getCoef(puente_id, nombre_sensor, eje)
        gb = df.groupby('reporte_dano_id')
        dfs = [gb.get_group(x) for x in gb.groups]
        coef_sensor = []
        for i in range(len(dfs)):
            column = dfs[i]["numero_modelo"]
            max_value = column.max()
            for j in range(max_value + 1):
                df2 = dfs[i][dfs[i]['numero_modelo'] == j].sort_values(by=['numero'])
                coef_sensor.append(np.array(df2['valor']))
        coefdf = pd.DataFrame(coef_sensor)
        mh = mahalanobis(x=coefdf, data=coefdf)
        if (analizeDamage(mh, 16, 3)):
            flag_damage = True
    return flag_damage

def analizeDamage(mahal, umbral_dist, umbral_num):
    count = 0
    for dist in mahal:
        if dist > umbral_dist:
            count += 1
    if count > umbral_num:
        return True
    else:
        return False

def addAnomallyAll(id_puente):
    try:
        sensores_de_puente = db.session.query(SensorInstalado.id.label("si"), DescripcionSensor.descripcion.label("nombre_sensor")).filter(SensorInstalado.id_estructura == id_puente, DescripcionSensor.id_sensor_instalado == SensorInstalado.id).order_by(SensorInstalado.id.desc())
        for sensor in sensores_de_puente:
            anomalia = AnomaliaPorHora(id_sensor_instalado = sensor.si, hora_calculo = datetime.now(), anomalia = getDamage(id_puente, sensor.nombre_sensor))
            db.session.add(anomalia)
            db.session.commit()
    except:
        db.session.rollback()

def addAnomally(id_puente, name):
    try:
        sensores_de_puente = db.session.query(SensorInstalado.id.label("si"), DescripcionSensor.descripcion.label("nombre_sensor")).filter(SensorInstalado.id_estructura == id_puente, DescripcionSensor.id_sensor_instalado == SensorInstalado.id, DescripcionSensor.descripcion == name).order_by(SensorInstalado.id.desc())
        for sensor in sensores_de_puente:
            anomalia = AnomaliaPorHora(id_sensor_instalado = sensor.si, hora_calculo = datetime.now(), anomalia = getDamage(id_puente, sensor.nombre_sensor))
            db.session.add(anomalia)
            db.session.commit()
    except:
        db.session.rollback()

def resetAllAnomally(id_puente):
    try:
        num_rows_deleted = db.session.query(AnomaliaPorHora).delete()
        db.session.commit()
        print("Filas Eliminadas = " + str(num_rows_deleted))
        sensores_de_puente = db.session.query(SensorInstalado.id.label("si")).filter(SensorInstalado.id_estructura == id_puente).order_by(SensorInstalado.id.desc())
        for sensor in sensores_de_puente:
            anomalia = AnomaliaPorHora(id_sensor_instalado = sensor.si, hora_calculo = datetime.now(), anomalia = False)
            db.session.add(anomalia)
            db.session.commit()
    except:
        db.session.rollback()

def propagation():
    _estados_sensor = ['Sin daño', 'Anomalía detectada', 'Anomalía intermitente', 'Daño detectado']
    _estados_elemento = ['Sin daño', 'Alerta puntual instantánea', 'Alerta puntual intermitente', 'Daño puntual', 'Alerta local instantánea', 'Alerta local intermitente', 'Daño local']
    _estados_estructura = ['Alerta general instantánea', 'Alerta general intermitente', 'Daño general']
    tiempo_ahora = datetime.now()
    flag_estado_sensor = 0           # 0 = Anomalia detectad, 1 = Anomalia intermitente, 2 = Daño detectado
    flag_estado_elemento = 0
    try:
        puentes = Estructura.query.filter_by(en_monitoreo = True)
        for puente in puentes:
            # print(puente.nombre)
            elementos = ElementoEstructural.query.filter_by(id_estructura = puente.id)
            dano_elemento_count = 0
            for elemento in elementos:
                # print(elemento.descripcion)
                dano_sensor_count = 0
                sensores = db.session.query(Estructura.id.label('id_puente'), Estructura.nombre.label('nombre_puente'), ElementoEstructural.id.label('id_elemento'), ElementoEstructural.descripcion.label('nombre_elemento'), SensorInstalado.id.label('si'), DescripcionSensor.descripcion.label('nombre')).filter(Estructura.id == puente.id, ElementoEstructural.id == elemento.id ,SensorInstalado.id_zona == elemento.id, SensorInstalado.id == DescripcionSensor.id_sensor_instalado)
                # print(len(sensores))
                for sensor in sensores:     # Se analiza cada sensor
                    # print(sensor.id_puente, sensor.nombre_puente, sensor.id_elemento, sensor.nombre_elemento, sensor.si, sensor.nombre)
                    dano_sensor = EstadoDanoSensor.query.filter_by(id_sensor_instalado = sensor.si).first()
                    anomalia = AnomaliaPorHora.query.filter_by(id_sensor_instalado = sensor.si).order_by(AnomaliaPorHora.hora_calculo.desc()).first()
                    if(not anomalia):
                        continue
                    tiempo_estado = tiempo_ahora - dano_sensor.diahora_calculo
                    tiempo_anomalia = tiempo_ahora - anomalia.hora_calculo
                    # print("TIEMPO ANOMALIA", tiempo_anomalia.days)
                    # print(anomalia.anomalia, dano_sensor.estado, dano_sensor_count)
                    # Anomalia Detectada
                    if(anomalia.anomalia and (dano_sensor.estado != _estados_sensor[1] or dano_sensor.estado != _estados_sensor[3]) and tiempo_estado.days <= 2):
                        dano_sensor.estado = _estados_sensor[1]
                        dano_sensor.diahora_calculo = tiempo_ahora
                        db.session.commit()
                        if(flag_estado_sensor == 0):
                            dano_sensor_count += 1
                    # Sin daño
                    elif(not anomalia.anomalia and dano_sensor.estado != _estados_sensor[0] and tiempo_anomalia.days >= 2):
                        dano_sensor.estado = _estados_sensor[0]
                        dano_sensor.diahora_calculo = tiempo_ahora
                        db.session.commit()
                    # Anomalia Intermitente
                    elif(not anomalia.anomalia and dano_sensor.estado != _estados_sensor[2] and tiempo_anomalia.days <= 2):
                        dano_sensor.estado = _estados_sensor[2]
                        dano_sensor.diahora_calculo = tiempo_ahora
                        db.session.commit()
                        if(flag_estado_sensor <= 1):
                            if(flag_estado_sensor < 1):
                                flag_estado_sensor = 1
                                dano_sensor_count = 0
                            dano_sensor_count += 1
                    # Daño detectado
                    elif(anomalia.anomalia and dano_sensor.estado != _estados_sensor[3] and tiempo_estado.days >= 2):
                        dano_sensor.estado = _estados_sensor[3]
                        dano_sensor.diahora_calculo = tiempo_ahora
                        db.session.commit()
                        if(flag_estado_sensor <= 2):
                            if(flag_estado_sensor < 2):
                                flag_estado_sensor = 2
                                dano_sensor_count = 0
                            dano_sensor_count += 1
                estado_elemento = EstadoDanoElemento.query.filter_by(id_elemento = elemento.id).first()
                if(not estado_elemento):
                    estado_elemento = EstadoDanoElemento(id_estructura = puente.id, id_elemento = elemento.id, diahora_calculo = tiempo_ahora, estado = _estados_elemento[0])
                    db.session.add(estado_elemento)
                    db.session.commit()
                    estado_elemento = EstadoDanoElemento.query.filter_by(id_elemento = elemento.id).first()
                if(dano_sensor_count == 0):
                    estado_elemento.diahora_calculo = tiempo_ahora
                    estado_elemento.estado = _estados_elemento[0]
                    db.session.commit()

                elif(flag_estado_sensor == 0):
                    if(dano_sensor_count == 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[1]
                        db.session.commit()

                    elif(dano_sensor_count > 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[4]
                        db.session.commit()

                    if(flag_estado_elemento == 0):
                        dano_elemento_count += 1

                elif(flag_estado_sensor == 1):
                    if(dano_sensor_count == 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[2]
                        db.session.commit()

                    elif(dano_sensor_count > 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[5]
                        db.session.commit()

                    if(flag_estado_elemento <= 1):
                        if(flag_estado_elemento < 1):
                            flag_estado_elemento = 1
                            dano_elemento_count = 0
                        dano_elemento_count += 1

                elif(flag_estado_sensor == 2):
                    if(dano_sensor_count == 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[3]
                        db.session.commit()

                    elif(dano_sensor_count > 1):
                        estado_elemento.diahora_calculo = tiempo_ahora
                        estado_elemento.estado = _estados_elemento[6]
                        db.session.commit()

                    if(flag_estado_elemento <= 2):
                        if(flag_estado_elemento < 2):
                            flag_estado_elemento = 2
                            dano_elemento_count = 0
                        dano_elemento_count += 1

            estado_estructura = EstadoDanoEstructura.query.filter_by(id_estructura = puente.id).first()
            if(not estado_estructura):
                estado_estructura = EstadoDanoEstructura(id_estructura = puente.id, diahora_calculo = datetime.now(), estado = _estados_estructura[0])
                db.session.add(estado_estructura)
                db.session.commit()
                estado_estructura = EstadoDanoEstructura.query.filter_by(id_estructura = puente.id).first()
            if(flag_estado_elemento == 1):
                if(dano_elemento_count > 1):
                    estado_estructura.diahora_calculo = tiempo_ahora
                    estado_estructura.estado = _estados_estructura[1]
                    db.session.commit()
            elif(flag_estado_elemento == 2):
                if(dano_elemento_count > 1):
                    estado_estructura.diahora_calculo = tiempo_ahora
                    estado_estructura.estado = _estados_estructura[2]
                    db.session.commit()
            else:
                estado_estructura.diahora_calculo = tiempo_ahora
                estado_estructura.estado = _estados_estructura[0]
                db.session.commit()

    except:
        print('Fallo consulta')
        db.session.rollback()
