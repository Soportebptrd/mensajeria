import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import folium
from streamlit_folium import st_folium
from fpdf import FPDF
import tempfile
import os

# ==============================
# CONFIGURACIÓN PARA STREAMLIT CLOUD
# ==============================
SHEET_ID = "1pXvN1PdQKfU8N5b8G5kPY5K8uhgCEbyt5EhKQt1-5ik"
WORKSHEET_NAME = "data"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Cuadrante geográfico (usaremos una aproximación simple sin Shapely)
cuadrante_coords = [
    [18.424446, -69.988949],
    [18.471448, -69.881432],
    [18.507120, -69.879462],
    [18.513480, -69.896407],
    [18.509511, -69.915497],
    [18.505557, -69.958319],
    [18.491012, -69.968240],
    [18.479161, -69.967454],
    [18.449450, -69.975032],
    [18.428729, -69.990303]
]

# ==============================
# AUTENTICACIÓN
# ==============================
def check_password():
    """Verifica la contraseña ingresada"""
    def password_entered():
        if (st.session_state["username"] == "idemefa" and 
            st.session_state["password"] == "idemefa"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        st.error("😕 Usuario o contraseña incorrectos")
        return False
    else:
        return True

# ==============================
# CONEXIÓN A GOOGLE SHEETS
# ==============================
@st.cache_data(ttl=300)
def cargar_datos():
    """Carga los datos desde Google Sheets usando secrets de Streamlit"""
    try:
        # Para Streamlit Cloud, las credenciales van en los secrets
        if 'gcp_service_account' in st.secrets:
            creds_dict = dict(st.secrets['gcp_service_account'])
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            # Para desarrollo local
            SERVICE_JSON_PATH = "service_account.json"
            if os.path.exists(SERVICE_JSON_PATH):
                creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
            else:
                st.error("❌ No se encontraron credenciales.")
                return pd.DataFrame()
        
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)
        datos = sheet.get_all_records()
        
        if not datos:
            st.warning("⚠️ No se encontraron datos en la hoja")
            return pd.DataFrame()
        
        df = pd.DataFrame(datos)
        
        # Convertir columnas
        if 'Fecha de llenar' in df.columns:
            df['Fecha de llenar'] = pd.to_datetime(df['Fecha de llenar'], errors='coerce')
        
        for col in ['Pago', 'Latitud', 'Longitud']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        st.success(f"✅ Datos cargados: {len(df)} registros")
        return df
        
    except Exception as e:
        st.error(f"❌ Error cargando datos: {str(e)}")
        return pd.DataFrame()

# ==============================
# FUNCIÓN SIMPLIFICADA PARA VERIFICAR CUADRANTE
# ==============================
def esta_en_cuadrante(lat, lon):
    """Verifica si un punto está dentro del cuadrante (aproximación simple)"""
    try:
        if pd.isna(lat) or pd.isna(lon):
            return False
        
        # Coordenadas límite del cuadrante
        lat_min = min(coord[0] for coord in cuadrante_coords)
        lat_max = max(coord[0] for coord in cuadrante_coords)
        lon_min = min(coord[1] for coord in cuadrante_coords)
        lon_max = max(coord[1] for coord in cuadrante_coords)
        
        return (lat_min <= lat <= lat_max) and (lon_min <= lon <= lon_max)
    except:
        return False

# ==============================
# FUNCIONES DE MAPA
# ==============================
def crear_mapa(df_filtrado):
    """Crea un mapa interactivo con los puntos y el cuadrante"""
    if df_filtrado.empty or 'Latitud' not in df_filtrado.columns or 'Longitud' not in df_filtrado.columns:
        return None
    
    # Filtrar filas con coordenadas válidas
    df_coordenadas = df_filtrado.dropna(subset=['Latitud', 'Longitud'])
    
    if df_coordenadas.empty:
        return None
    
    # Centro del mapa (Santo Domingo por defecto)
    lat_center = df_coordenadas['Latitud'].mean() if not df_coordenadas.empty else 18.4861
    lon_center = df_coordenadas['Longitud'].mean() if not df_coordenadas.empty else -69.9312
    
    mapa = folium.Map(location=[lat_center, lon_center], zoom_start=12)
    
    # Agregar cuadrante
    folium.Polygon(
        locations=cuadrante_coords,
        color='blue',
        fill=True,
        fill_color='blue',
        fill_opacity=0.1,
        popup='Cuadrante de Zona ($25)',
        tooltip='Zona de $25'
    ).add_to(mapa)
    
    # Agregar puntos
    for _, row in df_coordenadas.iterrows():
        # Color según el pago
        if row['Pago'] == 25:
            color = 'green'
            icono = 'ok-sign'
        elif row['Pago'] == 75:
            color = 'red'
            icono = 'remove-sign'
        else:
            color = 'gray'
            icono = 'question-sign'
        
        # Popup con información
        popup_html = f"""
        <div style="width: 250px;">
            <h4>Detalle de Entrega</h4>
            <p><b>Colaborador:</b> {row.get('Empleado', 'N/A')}</p>
            <p><b>Cliente:</b> {row.get('Nombre del cliente (usuario/codigo)', 'N/A')}</p>
            <p><b>Pago:</b> ${row.get('Pago', 0)}</p>
            <p><b>Fecha:</b> {row.get('Fecha de llenar', 'N/A')}</p>
            <p><b>Dirección:</b> {str(row.get('Dirección de envío', 'N/A'))[:50]}...</p>
        </div>
        """
        
        folium.Marker(
            location=[row['Latitud'], row['Longitud']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row.get('Empleado', 'N/A')} - ${row.get('Pago', 0)}",
            icon=folium.Icon(color=color, icon=icono, prefix='glyphicon')
        ).add_to(mapa)
    
    return mapa

# ==============================
# GENERACIÓN DE PDF
# ==============================
def generar_pdf(df_filtrado, fecha_inicio, fecha_fin, colaborador_seleccionado):
    """Genera un PDF con el reporte detallado"""
    
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 12)
            self.cell(0, 10, 'Reporte de Mensajería - IDEMEFA', 0, 1, 'C')
            self.ln(5)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')
    
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14)
    
    # Título
    pdf.cell(0, 10, 'REPORTE DETALLADO DE MENSAJERÍA', 0, 1, 'C')
    pdf.ln(5)
    
    # Información del reporte
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f'Período: {fecha_inicio.strftime("%d/%m/%Y")} - {fecha_fin.strftime("%d/%m/%Y")}', 0, 1)
    pdf.cell(0, 8, f'Colaborador: {colaborador_seleccionado if colaborador_seleccionado != "Total" else "Todos"}', 0, 1)
    pdf.cell(0, 8, f'Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1)
    pdf.ln(10)
    
    # Resumen por día
    if not df_filtrado.empty and 'Fecha de llenar' in df_filtrado.columns:
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'RESUMEN POR DÍA', 0, 1)
        pdf.ln(5)
        
        # Agrupar por fecha
        resumen_diario = df_filtrado.groupby(df_filtrado['Fecha de llenar'].dt.date).agg({
            'Empleado': 'count',
            'Pago': 'sum'
        }).reset_index()
        
        resumen_diario.columns = ['Fecha', 'Check-ins', 'Monto_Total']
        
        # Tabla de resumen
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(40, 10, 'Fecha', 1)
        pdf.cell(30, 10, 'Día', 1)
        pdf.cell(30, 10, 'Check-ins', 1)
        pdf.cell(40, 10, 'Monto Total', 1)
        pdf.ln()
        
        pdf.set_font('Arial', '', 10)
        total_general_checkins = 0
        total_general_monto = 0
        
        for _, fila in resumen_diario.iterrows():
            fecha = fila['Fecha']
            dia_semana = fecha.strftime('%A')
            dias_esp = {
                'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
                'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado'
            }
            
            pdf.cell(40, 10, fecha.strftime('%d/%m/%Y'), 1)
            pdf.cell(30, 10, dias_esp.get(dia_semana, dia_semana), 1)
            pdf.cell(30, 10, str(fila['Check-ins']), 1)
            pdf.cell(40, 10, f"${fila['Monto_Total']:,.2f}", 1)
            pdf.ln()
            
            total_general_checkins += fila['Check-ins']
            total_general_monto += fila['Monto_Total']
        
        # Totales
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(70, 10, 'TOTAL GENERAL', 1)
        pdf.cell(30, 10, str(total_general_checkins), 1)
        pdf.cell(40, 10, f"${total_general_monto:,.2f}", 1)
        pdf.ln(15)
    
    # Detalle de entregas
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, 'DETALLE DE ENTREGAS', 0, 1)
    pdf.ln(5)
    
    # Columnas para el detalle
    columnas_pdf = [
        'Dirección de envío', 
        'Lugar de envío', 
        'Nombre del cliente (usuario/codigo)',
        'Nombre de quien recibe (maria/secretaria, juan/asistente, miguel ruiz/doctor)',
        'Pago'
    ]
    
    # Verificar qué columnas están disponibles
    columnas_disponibles = [col for col in columnas_pdf if col in df_filtrado.columns]
    
    if columnas_disponibles:
        anchos = [60, 25, 35, 35, 15]
        
        # Encabezados de tabla detalle
        pdf.set_font('Arial', 'B', 8)
        for i, columna in enumerate(columnas_disponibles):
            nombre_corto = columna[:20] + '...' if len(columna) > 20 else columna
            pdf.cell(anchos[i], 10, nombre_corto, 1)
        pdf.ln()
        
        # Datos detallados
        pdf.set_font('Arial', '', 7)
        for _, fila in df_filtrado.iterrows():
            valores = []
            for columna in columnas_disponibles:
                valor = str(fila.get(columna, ''))
                if columna == 'Lugar de envío' and valor.upper() != 'IDEMEFA':
                    valor = ''
                elif len(valor) > 30:
                    valor = valor[:30] + '...'
                valores.append(valor)
            
            for i, valor in enumerate(valores):
                pdf.cell(anchos[i], 8, valor, 1)
            pdf.ln()
            
            # Verificar si necesita nueva página
            if pdf.get_y() > 250:
                pdf.add_page()
                pdf.set_font('Arial', 'B', 8)
                for i, columna in enumerate(columnas_disponibles):
                    nombre_corto = columna[:20] + '...' if len(columna) > 20 else columna
                    pdf.cell(anchos[i], 10, nombre_corto, 1)
                pdf.ln()
                pdf.set_font('Arial', '', 7)
    
    return pdf

# ==============================
# INTERFAZ PRINCIPAL
# ==============================
def main_app():
    st.set_page_config(page_title="Reporte Mensajería", page_icon="🚚", layout="wide")
    
    st.title("🚚 Reporte de Mensajería - IDEMEFA")
    st.markdown("---")
    
    # Cargar datos
    df = cargar_datos()
    
    if df.empty:
        st.error("No se pudieron cargar los datos.")
        return
    
    # Sidebar con filtros
    st.sidebar.header("Filtros")
    
    # Filtro de fechas
    if 'Fecha de llenar' in df.columns:
        fecha_min = df['Fecha de llenar'].min()
        fecha_max = df['Fecha de llenar'].max()
    else:
        fecha_min = datetime.now() - timedelta(days=30)
        fecha_max = datetime.now()
    
    rango_fechas = st.sidebar.date_input(
        "Rango de fechas",
        value=(fecha_min.date(), fecha_max.date()),
        min_value=fecha_min.date(),
        max_value=fecha_max.date()
    )
    
    # Filtro de colaboradores
    colaboradores = ['Total'] 
    if 'Empleado' in df.columns:
        colaboradores += sorted(df['Empleado'].dropna().unique().tolist())
    
    colaborador_seleccionado = st.sidebar.selectbox("Colaborador", colaboradores)
    
    # Aplicar filtros
    if len(rango_fechas) == 2 and 'Fecha de llenar' in df.columns:
        fecha_inicio = pd.to_datetime(rango_fechas[0])
        fecha_fin = pd.to_datetime(rango_fechas[1]) + timedelta(days=1)
        
        df_filtrado = df[
            (df['Fecha de llenar'] >= fecha_inicio) & 
            (df['Fecha de llenar'] <= fecha_fin)
        ]
        
        if colaborador_seleccionado != 'Total' and 'Empleado' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Empleado'] == colaborador_seleccionado]
    else:
        df_filtrado = df.copy()
    
    # Métricas principales
    st.subheader("Resumen General")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_entregas = len(df_filtrado)
        st.metric("📦 Total Entregas", total_entregas)
    
    with col2:
        total_pago = df_filtrado['Pago'].sum() if 'Pago' in df_filtrado.columns and not df_filtrado.empty else 0
        st.metric("💰 Monto Total", f"${total_pago:,.2f}")
    
    with col3:
        entregas_25 = len(df_filtrado[(df_filtrado['Pago'] == 25)]) if 'Pago' in df_filtrado.columns and not df_filtrado.empty else 0
        st.metric("🟢 Entregas $25", entregas_25)
    
    with col4:
        entregas_75 = len(df_filtrado[(df_filtrado['Pago'] == 75)]) if 'Pago' in df_filtrado.columns and not df_filtrado.empty else 0
        st.metric("🔴 Entregas $75", entregas_75)
    
    # Mapa interactivo
    st.subheader("🗺️ Mapa de Entregas")
    if not df_filtrado.empty:
        mapa = crear_mapa(df_filtrado)
        if mapa:
            st_folium(mapa, width=1200, height=500)
        else:
            st.warning("No hay datos con coordenadas válidas para mostrar en el mapa.")
    else:
        st.info("No hay datos para mostrar en el mapa con los filtros seleccionados.")
    
    # Tabla de datos
    st.subheader("📋 Detalle de Entregas")
    
    # Columnas a mostrar
    columnas_mostrar = [
        'Empleado', 'Fecha de llenar', 'Dirección de envío', 
        'Lugar de envío', 'Nombre del cliente (usuario/codigo)',
        'Nombre de quien recibe (maria/secretaria, juan/asistente, miguel ruiz/doctor)',
        'Pago', 'Latitud', 'Longitud'
    ]
    
    columnas_disponibles = [col for col in columnas_mostrar if col in df_filtrado.columns]
    
    if not df_filtrado.empty:
        st.dataframe(df_filtrado[columnas_disponibles], use_container_width=True)
        
        # Botón para generar PDF
        st.subheader("📄 Generar Reporte")
        if st.button("Generar Reporte PDF", type="primary"):
            with st.spinner("Generando PDF..."):
                try:
                    pdf = generar_pdf(df_filtrado, fecha_inicio, fecha_fin, colaborador_seleccionado)
                    
                    # Guardar PDF temporal
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        pdf.output(tmp_file.name)
                        
                        # Leer el archivo y crear botón de descarga
                        with open(tmp_file.name, "rb") as file:
                            pdf_bytes = file.read()
                        
                        st.download_button(
                            label="⬇️ Descargar PDF",
                            data=pdf_bytes,
                            file_name=f"reporte_mensajeria_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            type="primary"
                        )
                    
                    # Limpiar archivo temporal
                    os.unlink(tmp_file.name)
                    st.success("✅ PDF generado correctamente")
                    
                except Exception as e:
                    st.error(f"❌ Error generando PDF: {str(e)}")
    else:
        st.info("No hay datos para mostrar con los filtros seleccionados.")

# ==============================
# EJECUCIÓN PRINCIPAL
# ==============================
if __name__ == "__main__":
    if check_password():
        main_app()
