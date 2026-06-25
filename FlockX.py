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
DATOS_LEGAJOS = None # Variable global para el archivo de legajos

def procesar_dataframe(df): # Parsea el archivo 
    """Limpia y estructura el DataFrame recibido."""
    df = df.replace('-', 'Pendiente')
    df.columns = df.columns.str.strip()

    column_map = {col.lower(): col for col in df.columns}

    def buscar_columna(posibles_nombres):
        for nombre in posibles_nombres:
            if nombre.lower() in column_map:
                return column_map[nombre.lower()]
        return None

    col_nombre_completo = buscar_columna([
        'Nombre Completo', 'Nombre completo', 'Full Name', 'Full name',
        'FullName', 'name', 'Name', 'Nombre'
    ])
    col_nombre = buscar_columna(['Nombre', 'First name', 'Firstname', 'First Name', 'Given Name'])
    col_apellido = buscar_columna(['Apellido(s)', 'Apellido', 'Last name', 'Lastname', 'Last Name', 'Surname'])
    col_correo = buscar_columna([
        'Dirección de correo', 'Correo electrónico', 'Correo Electronico', 'Email', 'E-mail',
        'Email address', 'Email Address', 'correo', 'mail'
    ])
    col_legajo = buscar_columna(['Legajo', 'legajo'])

    if col_nombre_completo and col_nombre_completo in df.columns:
        df['Nombre Completo'] = df[col_nombre_completo].astype(str).str.strip()
    elif col_nombre and col_apellido and col_nombre in df.columns and col_apellido in df.columns:
        df['Nombre Completo'] = df[col_nombre].astype(str).str.strip() + ' ' + df[col_apellido].astype(str).str.strip()
    elif col_nombre and col_nombre in df.columns:
        df['Nombre Completo'] = df[col_nombre].astype(str).str.strip()
    elif col_apellido and col_apellido in df.columns:
        df['Nombre Completo'] = df[col_apellido].astype(str).str.strip()
    else:
        df['Nombre Completo'] = ''

    if col_correo and col_correo in df.columns:
        df['Dirección de correo'] = df[col_correo].astype(str).str.strip()
    else:
        # Intentar detectar columna de correo automáticamente
        correo_detectado = None
        for col in df.columns:
            if df[col].astype(str).str.contains('@', na=False).any():
                correo_detectado = col
                break
        if correo_detectado:
            df['Dirección de correo'] = df[correo_detectado].astype(str).str.strip()
        else:
            df['Dirección de correo'] = ''

    if col_legajo and col_legajo in df.columns:
        df['Legajo'] = df[col_legajo].astype(str).str.strip()
    elif 'Legajo' not in df.columns:
        df['Legajo'] = ''

    def buscar_columna_alerta():
        for col in df.columns:
            palabras = [p for p in str(col).strip().split() if p]
            if len(palabras) >= 3:
                primeras = ' '.join(palabras[:3]).lower()
                if primeras == 'estado de alerta':
                    return col
        return None

    col_alerta = buscar_columna_alerta()

    def normalizar_alerta(valor):
        texto = str(valor).strip()
        if texto == '' or texto.lower() in ['nan', 'none', 'pendiente']:
            return 0, 'No disponible'

        try:
            numero = int(float(texto))
        except (ValueError, TypeError):
            numero = None

        lower = texto.lower()
        if numero == 3 or 'situación crítica' in lower or 'situacion critica' in lower or ('crítica' in lower and 'media' not in lower) or 'criti' in lower and 'media' not in lower:
            return 3, 'Situación Crítica'
        if numero == 2 or 'criticidad media' in lower or 'media' in lower:
            return 2, 'Criticidad media'
        if numero == 1 or 'fuera de criticidad' in lower or 'fuera' in lower or 'no crítico' in lower or 'sin criticidad' in lower:
            return 1, 'Fuera de criticidad'
        if numero in [1, 2, 3]:
            etiquetas = {1: 'Fuera de criticidad', 2: 'Criticidad media', 3: 'Situación Crítica'}
            return numero, etiquetas[numero]
        if 'crítica' in lower or 'critico' in lower:
            return 3, 'Situación Crítica'
        return 0, 'No disponible'

    if col_alerta and col_alerta in df.columns:
        df['Estado de Alerta'] = df[col_alerta].astype(str).str.strip()
    elif 'Estado de Alerta' not in df.columns:
        df['Estado de Alerta'] = ''

    niveles = []
    etiquetas = []
    for valor in df['Estado de Alerta']:
        nivel, etiqueta = normalizar_alerta(valor)
        niveles.append(nivel)
        etiquetas.append(etiqueta)

    df['AlertaNivel'] = niveles
    df['AlertaEtiqueta'] = etiquetas

    return df

def procesar_base_datos(df):
    """Procesa el DataFrame de la base de datos de Moodle."""
    df = df.replace('-', 'Pendiente')
    if 'Legajo' in df.columns:
        df['Legajo'] = df['Legajo'].astype(str).str.strip()
    
    # Agregar columna de coherencia entre estado y nota
    def verificar_coherencia(row):
        """Verifica si hay coherencia entre el estado y la nota."""
        try:
            nota = float(row['Nota'])
        except (ValueError, TypeError):
            return 'Incoherente'

        if nota < 0 or nota > 10:
            return 'Incoherente'

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

def procesar_legajos(df):
    """Procesa el archivo de legajos y normaliza las columnas."""
    df = df.replace('-', 'Pendiente')
    
    if 'Nombre completo del usuario' in df.columns:
        df['Nombre Completo'] = df['Nombre completo del usuario']
    if '(legajo) Ingresá tu número de legajo' in df.columns:
        df['Legajo'] = df['(legajo) Ingresá tu número de legajo']
    if 'Legajo' in df.columns:
        df['Legajo'] = df['Legajo'].astype(str).str.strip()
    if 'Dirección de correo' in df.columns:
        df['Dirección de correo'] = df['Dirección de correo'].astype(str).str.strip()
    return df

@app.route('/') # Renderiza el lander para cargar archivos
def index():
    """Ruta principal: Landing page para cargar archivos."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS, DATOS_LEGAJOS
    
    # Verificar si ya hay datos cargados
    hay_datos = DATOS_ALUMNOS is not None or DATOS_BASE_DATOS is not None or DATOS_LEGAJOS is not None
    
    return render_template('index.html', hay_datos=hay_datos)

@app.route('/analisis')
def analisis():
    """Página de análisis con listados de estudiantes y materias."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS, DATOS_LEGAJOS
    
    estudiantes = []
    registros_base_datos = []
    materias_unicas = []
    cantidad_legajos = 0
    legajo_por_correo = {}
    
    if DATOS_LEGAJOS is not None and 'Dirección de correo' in DATOS_LEGAJOS.columns and 'Legajo' in DATOS_LEGAJOS.columns:
        legajo_por_correo = DATOS_LEGAJOS.set_index('Dirección de correo')['Legajo'].astype(str).str.strip().to_dict()
        cantidad_legajos = len(DATOS_LEGAJOS)
    
    if DATOS_ALUMNOS is not None:
        estudiantes = DATOS_ALUMNOS.to_dict('records')
        for est in estudiantes:
            correo = str(est.get('Dirección de correo', '')).strip()
            est['Legajo'] = legajo_por_correo.get(correo, '')
            est['_nota_orden'] = float('inf')

    materia_stats = []

    if DATOS_BASE_DATOS is not None:
        df_coherente = DATOS_BASE_DATOS[DATOS_BASE_DATOS['Coherencia'] == 'Ok'].copy()
        df_coherente['Nota_num'] = pd.to_numeric(df_coherente['Nota'], errors='coerce')

        notas_por_legajo = {}
        if 'Legajo' in df_coherente.columns:
            df_coherente['Legajo'] = df_coherente['Legajo'].astype(str).str.strip()
            notas_por_legajo = df_coherente.groupby('Legajo')['Nota_num'].mean().to_dict()

        correo_col = None
        for nombre in ['Dirección de correo', 'Correo electrónico', 'Email', 'E-mail', 'correo']:
            if nombre in df_coherente.columns:
                correo_col = nombre
                break

        notas_por_correo = {}
        if correo_col is not None:
            notas_por_correo = df_coherente.groupby(correo_col)['Nota_num'].mean().to_dict()

        for est in estudiantes:
            legajo = str(est.get('Legajo', '')).strip()
            correo = str(est.get('Dirección de correo', '')).strip()
            if legajo and legajo in notas_por_legajo:
                est['_nota_orden'] = notas_por_legajo[legajo]
            elif correo and correo in notas_por_correo:
                est['_nota_orden'] = notas_por_correo[correo]

        estudiantes.sort(key=lambda e: (-int(e.get('AlertaNivel', 0)), e.get('_nota_orden', float('inf')), e.get('Nombre Completo', '')))

        # Ordenar por Legajo y convertir a lista de registros
        df_ordenado = DATOS_BASE_DATOS.sort_values('Legajo')
        registros_base_datos = df_ordenado.to_dict('records')

        # Filtrar únicamente los registros coherentes para el análisis de materias
        df_coherente = DATOS_BASE_DATOS[DATOS_BASE_DATOS['Coherencia'] == 'Ok']
        materias_unicas = sorted(df_coherente['Asignatura'].dropna().unique().tolist())

        for materia in materias_unicas:
            df_materia = df_coherente[df_coherente['Asignatura'] == materia]
            if df_materia.empty:
                continue

            if 'Legajo' in df_materia.columns:
                cantidad_estudiantes = df_materia['Legajo'].astype(str).str.strip().nunique()
            else:
                cantidad_estudiantes = len(df_materia)

            df_materia = df_materia.copy()
            df_materia['Nota_num'] = pd.to_numeric(df_materia['Nota'], errors='coerce')
            promedio_nota = df_materia['Nota_num'].mean()

            desaprobados = df_materia[df_materia['Estado'].astype(str).str.lower().str.contains('desaprobado', na=False)]
            porcentaje_desaprobados = 0
            if len(df_materia) > 0:
                porcentaje_desaprobados = round((len(desaprobados) / len(df_materia)) * 100, 1)

            materia_stats.append({
                'Asignatura': materia,
                'CantidadEstudiantes': cantidad_estudiantes,
                'PorcentajeDesaprobados': porcentaje_desaprobados,
                'NotaPromedio': round(promedio_nota, 2) if pd.notna(promedio_nota) else None
            })

    return render_template('analisis.html', 
                         estudiantes=estudiantes, 
                         registros_base_datos=registros_base_datos,
                         materia_stats=materia_stats,
                         cantidad_legajos=cantidad_legajos)

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

@app.route('/cargar_legajos', methods=['POST'])
def cargar_legajos():
    """Recibe el archivo de legajos y lo procesa."""
    global DATOS_LEGAJOS
    
    if 'archivo_legajos' not in request.files:
        return jsonify({'exito': False, 'mensaje': 'No se encontró el archivo'}), 400
        
    file = request.files['archivo_legajos']
    
    if file.filename == '':
        return jsonify({'exito': False, 'mensaje': 'Archivo no seleccionado'}), 400
        
    if file:
        try:
            if file.filename.endswith('.csv'):
                df_crudo = pd.read_csv(file)
            else:
                return jsonify({'exito': False, 'mensaje': 'El archivo debe ser .csv'}), 400
                
            DATOS_LEGAJOS = procesar_legajos(df_crudo)
            return jsonify({
                'exito': True,
                'mensaje': f'Archivo cargado: {file.filename}',
                'cantidad_legajos': len(DATOS_LEGAJOS)
            })
        except Exception as e:
            return jsonify({'exito': False, 'mensaje': f'Error al procesar: {str(e)}'}), 500

@app.route('/estado_archivos')
def estado_archivos():
    """Retorna el estado de los archivos cargados."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS, DATOS_LEGAJOS
    
    return jsonify({
        'archivo_principal': DATOS_ALUMNOS is not None,
        'archivo_base_datos': DATOS_BASE_DATOS is not None,
        'archivo_legajos': DATOS_LEGAJOS is not None,
        'listo_para_analisis': (DATOS_ALUMNOS is not None) and (DATOS_BASE_DATOS is not None) and (DATOS_LEGAJOS is not None)
    })

@app.route('/estudiante/<correo>')
def detalle_estudiante(correo):
    """Muestra el perfil de un estudiante específico y sus notas por legajo."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS, DATOS_LEGAJOS
    
    if DATOS_ALUMNOS is None:
        return redirect(url_for('index'))
        
    estudiante_filtrado = DATOS_ALUMNOS[DATOS_ALUMNOS['Dirección de correo'] == correo]
    
    if estudiante_filtrado.empty:
        return "Estudiante no encontrado", 404

    estudiante = estudiante_filtrado.to_dict('records')[0]
    legajo = ''
    notas_legajo = []

    if DATOS_LEGAJOS is not None and 'Dirección de correo' in DATOS_LEGAJOS.columns and 'Legajo' in DATOS_LEGAJOS.columns:
        legajo_filtrado = DATOS_LEGAJOS[DATOS_LEGAJOS['Dirección de correo'] == correo]
        if not legajo_filtrado.empty:
            legajo = str(legajo_filtrado.iloc[0]['Legajo']).strip()
    
    if legajo and DATOS_BASE_DATOS is not None and 'Legajo' in DATOS_BASE_DATOS.columns:
        notas_legajo = DATOS_BASE_DATOS[DATOS_BASE_DATOS['Legajo'].astype(str).str.strip() == legajo].to_dict('records')

    indicadores = []
    if DATOS_ALUMNOS is not None:
        metadatos = {
            'Nombre Completo', 'Nombre', 'Apellido(s)', 'Apellido',
            'Dirección de correo', 'Email', 'E-mail', 'Email address',
            'correo', 'mail', 'Legajo', 'Estado de Alerta',
            'AlertaNivel', 'AlertaEtiqueta'
        }
        indicadores = [col for col in DATOS_ALUMNOS.columns if col not in metadatos]

    return render_template('detalle.html', estudiante=estudiante, legajo=legajo, notas_legajo=notas_legajo, indicadores=indicadores)

@app.route('/limpiar')
def limpiar_datos():
    """Permite "cerrar los archivos" actuales para cargar unos nuevos."""
    global DATOS_ALUMNOS, DATOS_BASE_DATOS, DATOS_LEGAJOS
    DATOS_ALUMNOS = None
    DATOS_BASE_DATOS = None
    DATOS_LEGAJOS = None
    return redirect(url_for('index'))

def abrir_navegador():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    Timer(1, abrir_navegador).start()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)