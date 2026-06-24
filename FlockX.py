import sys
import os
import webbrowser
from threading import Timer
from flask import Flask, render_template, request, redirect, url_for, jsonify
import pandas as pd

if getattr(sys, 'frozen', False): # Detección de si el script está corriendo como .py o como .exe compilado
    directorio_interno = sys._MEIPASS
else:
    directorio_interno = os.path.abspath(".")

app = Flask(__name__, template_folder=os.path.join(directorio_interno, 'templates'),static_folder=os.path.join(directorio_interno, 'static'))

DATOS_ALUMNOS = None # Variable global del archivo cargado.
DATOS_BASE_DATOS = None # Variable global para el archivo de la base de datos de Moodle

def procesar_dataframe(df): # Parsea el archivo 
    """Limpia y estructura el DataFrame recibido."""
    df = df.replace('-', 'Pendiente')
    df['Nombre Completo'] = df['Nombre'] + ' ' + df['Apellido(s)']
    return df

def procesar_base_datos(df):
    """Procesa el DataFrame de la base de datos de Moodle."""
    df = df.replace('-', 'Pendiente')
    
    # Agregar columna de coherencia entre estado y nota
    def verificar_coherencia(row):
        """Verifica si hay coherencia entre el estado y la nota."""
        try:
            nota = float(row['Nota'])
        except (ValueError, TypeError):
            # Si la nota no es un número, considerarla coherente por defecto
            return 'Ok'
        
        estado = str(row['Estado']).lower()
        
        # Estados de aprobación vs estados de desaprobación
        if 'desaprobado' in estado:
            # Si está desaprobado, la nota debería ser < 4
            if nota >= 4:
                return 'Incoherente'
        else:
            # Si está aprobado, promocionado o habilitado, la nota debería ser >= 4
            if nota < 4:
                return 'Incoherente'
        
        return 'Ok'
    
    df['Coherencia'] = df.apply(verificar_coherencia, axis=1)
    return df

@app.route('/') # Renderiza el lander para cargar archivos
def index():
    """Ruta principal: Landing page para cargar archivos."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS
    
    # Verificar si ya hay datos cargados
    hay_datos = DATOS_ALUMNOS is not None or DATOS_BASE_DATOS is not None
    
    return render_template('index.html', hay_datos=hay_datos)

@app.route('/analisis')
def analisis():
    """Página de análisis con listados de estudiantes y materias."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS
    
    estudiantes = []
    registros_base_datos = []
    materias_unicas = []
    
    if DATOS_ALUMNOS is not None:
        estudiantes = DATOS_ALUMNOS.to_dict('records')
    
    if DATOS_BASE_DATOS is not None:
        # Ordenar por Legajo y convertir a lista de registros
        df_ordenado = DATOS_BASE_DATOS.sort_values('Legajo')
        registros_base_datos = df_ordenado.to_dict('records')
        
        # Obtener materias únicas ordenadas alfabéticamente
        materias_unicas = sorted(DATOS_BASE_DATOS['Asignatura'].unique().tolist())
    
    return render_template('analisis.html', 
                         estudiantes=estudiantes, 
                         registros_base_datos=registros_base_datos,
                         materias_unicas=materias_unicas)

@app.route('/cargar', methods=['POST'])
def cargar_archivo():
    """Recibe el archivo principal desde la interfaz web y lo procesa."""
    global DATOS_ALUMNOS
    
    if 'archivo_moodle' not in request.files:
        return jsonify({'exito': False, 'mensaje': 'No se encontró el archivo'}), 400
        
    file = request.files['archivo_moodle']
    
    if file.filename == '':
        return jsonify({'exito': False, 'mensaje': 'Archivo no seleccionado'}), 400
        
    if file:
        try:
            # Detectamos la extensión para saber cómo leerlo con Pandas
            if file.filename.endswith('.xlsx'):
                df_crudo = pd.read_excel(file)
            elif file.filename.endswith('.csv'):
                df_crudo = pd.read_csv(file)
            else:
                return jsonify({'exito': False, 'mensaje': 'Formato no soportado'}), 400
                
            # Procesamos y guardamos en la variable global
            DATOS_ALUMNOS = procesar_dataframe(df_crudo)
            return jsonify({
                'exito': True, 
                'mensaje': f'Archivo cargado: {file.filename}',
                'cantidad_estudiantes': len(DATOS_ALUMNOS)
            })
            
        except Exception as e:
            return jsonify({'exito': False, 'mensaje': f'Error al procesar: {str(e)}'}), 500

@app.route('/cargar_base_datos', methods=['POST'])
def cargar_base_datos():
    """Recibe el archivo de la base de datos de Moodle y lo procesa."""
    global DATOS_BASE_DATOS
    
    if 'archivo_base_datos' not in request.files:
        return jsonify({'exito': False, 'mensaje': 'No se encontró el archivo'}), 400
        
    file = request.files['archivo_base_datos']
    
    if file.filename == '':
        return jsonify({'exito': False, 'mensaje': 'Archivo no seleccionado'}), 400
        
    if file:
        try:
            # Este archivo debe ser CSV (base de datos de Moodle)
            if file.filename.endswith('.csv'):
                df_crudo = pd.read_csv(file)
            else:
                return jsonify({'exito': False, 'mensaje': 'El archivo debe ser .csv'}), 400
                
            # Procesamos y guardamos en la variable global
            DATOS_BASE_DATOS = procesar_base_datos(df_crudo)
            return jsonify({
                'exito': True, 
                'mensaje': f'Archivo cargado: {file.filename}',
                'cantidad_registros': len(DATOS_BASE_DATOS)
            })
            
        except Exception as e:
            return jsonify({'exito': False, 'mensaje': f'Error al procesar: {str(e)}'}), 500

@app.route('/estado_archivos')
def estado_archivos():
    """Retorna el estado de los archivos cargados."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS
    
    return jsonify({
        'archivo_principal': DATOS_ALUMNOS is not None,
        'archivo_base_datos': DATOS_BASE_DATOS is not None,
        'ambos_cargados': (DATOS_ALUMNOS is not None) and (DATOS_BASE_DATOS is not None)
    })

@app.route('/estudiante/<correo>')
def detalle_estudiante(correo):
    """Muestra el perfil de un estudiante específico."""
    global DATOS_ALUMNOS
    
    if DATOS_ALUMNOS is None:
        return redirect(url_for('index'))
        
    estudiante_filtrado = DATOS_ALUMNOS[DATOS_ALUMNOS['Dirección de correo'] == correo]
    
    if not estudiante_filtrado.empty:
        estudiante = estudiante_filtrado.to_dict('records')[0]
        return render_template('detalle.html', estudiante=estudiante)
    else:
        return "Estudiante no encontrado", 404

@app.route('/limpiar')
def limpiar_datos():
    """Permite "cerrar los archivos" actuales para cargar unos nuevos."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS
    DATOS_ALUMNOS = None
    DATOS_BASE_DATOS = None
    return redirect(url_for('index'))

def abrir_navegador():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    Timer(1, abrir_navegador).start()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)