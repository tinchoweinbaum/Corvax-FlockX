import sys
import os
import webbrowser
from threading import Timer
from flask import Flask, render_template, request, redirect, url_for
import pandas as pd

if getattr(sys, 'frozen', False): # Detección de si el script está corriendo como .py o como .exe compilado
    directorio_interno = sys._MEIPASS
else:
    directorio_interno = os.path.abspath(".")

app = Flask(__name__, template_folder=os.path.join(directorio_interno, 'templates'),static_folder=os.path.join(directorio_interno, 'static'))

DATOS_ALUMNOS = None # Variable global del archivo cargado.

def procesar_dataframe(df): # Parsea el archivo 
    """Limpia y estructura el DataFrame recibido."""
    df = df.replace('-', 'Pendiente')
    df['Nombre Completo'] = df['Nombre'] + ' ' + df['Apellido(s)']
    return df

@app.route('/') # Renderiza una plantilla u otra dependiendo de si ya se cargó un archivo o no.
def index():
    """Ruta principal: Muestra el botón de carga o la lista si ya hay datos."""
    global DATOS_ALUMNOS
    
    if DATOS_ALUMNOS is None:
        # Si no se cargó ningún archivo, mostramos la pantalla de bienvenida/carga
        return render_template('index.html', estudiantes=[])
    
    # Si ya hay datos, los enviamos a la interfaz
    estudiantes = DATOS_ALUMNOS.to_dict('records')
    return render_template('index.html', estudiantes=estudiantes)

@app.route('/cargar', methods=['POST'])
def cargar_archivo():
    """Recibe el archivo desde la interfaz web y lo procesa."""
    global DATOS_ALUMNOS
    
    if 'archivo_moodle' not in request.files:
        return redirect(url_for('index'))
        
    file = request.files['archivo_moodle']
    
    if file.filename == '':
        return redirect(url_for('index'))
        
    if file:
        try:
            # Detectamos la extensión para saber cómo leerlo con Pandas
            if file.filename.endswith('.xlsx'):
                df_crudo = pd.read_excel(file)
            elif file.filename.endswith('.csv'):
                df_crudo = pd.read_csv(file)
            else:
                return "Formato de archivo no soportado. Cargue un archivo .csv o .xlsx", 400
                
            # Procesamos y guardamos en la variable global
            DATOS_ALUMNOS = procesar_dataframe(df_crudo)
            return redirect(url_for('index'))
            
        except Exception as e:
            return f"Error al procesar el archivo: {e}", 500

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
    """Permite "cerrar el archivo" actual para cargar uno nuevo."""
    global DATOS_ALUMNOS
    DATOS_ALUMNOS = None
    return redirect(url_for('index'))

def abrir_navegador():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    Timer(1, abrir_navegador).start()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)