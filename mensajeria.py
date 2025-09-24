import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import folium
from streamlit_folium import st_folium
from fpdf import FPDF
import tempfile
import os
import requests
import io
from branca.element import Element

# ==============================
# CONFIGURACIÓN
# ==============================
# URL pública del Google Sheet (publicada como CSV)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1pXvN1PdQKfU8N5b8G5kPY5K8uhgCEbyt5EhKQt1-5ik/export?format=csv"

# Coordenadas del cuadrante (polígono)
CUADRANTE_COORDS = [
    [18.470910, -69.881842],
    [18.467871, -69.889721],
    [18.464781, -69.893714],
    [18.461370, -69.899534],
    [18.460956, -69.902208],
    [18.456405, -69.913385],
    [18.446481, -69.924817],
    [18.426873, -69.971667],
    [18.426485, -69.981364],
    [18.424306, -69.989173],
    [18.428616, -69.990499],
    [18.442414, -69.977843],
    [18.451322, -69.974168],
    [18.461973, -69.969014],
    [18.484094, -69.967227],
    [18.486417, -69.969167],
    [18.489507, -69.969121],
	[18.494270, -69.964476],
 	[18.507445, -69.960890],  
 	[18.520477, -69.936902],	 
    [18.509636, -69.915537],
    [18.513721, -69.896844],
    [18.507693, -69.878878],
    [18.500750, -69.875250],
    [18.494284, -69.877883],
    [18.488074, -69.883216],
    [18.471752, -69.881296],
]

# Columnas esperadas para la tabla
COLUMNAS_TABLA = [
    'Empleado',
    'Tipo',
    'Dirección de envío',
    'Fecha de llenar',
    'Nombre del cliente (usuario/codigo)',
    'Nombre de quien recibe (maria/secretaria, juan/asistente, miguel ruiz/doctor)',
    'Pago',
]

# ==============================
# UTILIDADES
# ==============================
@st.cache_data(ttl=300)
def cargar_datos(url: str) -> pd.DataFrame:
    """Descarga el CSV publicado del Google Sheet y normaliza columnas clave."""
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))

        # Normalización de columnas conocidas
        if 'Fecha de llenar' in df.columns:
            df['Fecha de llenar'] = pd.to_datetime(df['Fecha de llenar'], errors='coerce')
        if 'Pago' in df.columns:
            df['Pago'] = pd.to_numeric(df['Pago'], errors='coerce')
        if 'Latitud' in df.columns:
            df['Latitud'] = pd.to_numeric(df['Latitud'], errors='coerce')
        if 'Longitud' in df.columns:
            df['Longitud'] = pd.to_numeric(df['Longitud'], errors='coerce')

        # Quitar filas completamente vacías
        df = df.dropna(how='all')
        return df
    except Exception as e:
        st.error(f"❌ Error cargando datos de Google Sheets: {e}")
        st.info("Verifica que la hoja esté publicada en Archivo → Compartir → Publicar en la web → Hoja 'data' en formato CSV")
        return pd.DataFrame()


def crear_mapa(df: pd.DataFrame):
    """Construye un mapa Folium con polígono/leyenda y marcadores coloreados por Pago (25/75)."""
    cols_coord_ok = {'Latitud', 'Longitud'}.issubset(set(df.columns))
    if df.empty or not cols_coord_ok:
        return None

    df = df.dropna(subset=['Latitud', 'Longitud'])
    if df.empty:
        return None

    lat_center = df['Latitud'].mean()
    lon_center = df['Longitud'].mean()

    m = folium.Map(location=[lat_center, lon_center], zoom_start=12, control_scale=True)

    # Polígono del cuadrante (zona $25)
    folium.Polygon(
        locations=CUADRANTE_COORDS,
        color='blue',
        weight=2,
        fill=True,
        fill_color='blue',
        fill_opacity=0.10,
        popup='Cuadrante de Zona ($25)',
        tooltip='Zona de $25',
    ).add_to(m)

    # Marcadores
    for _, row in df.iterrows():
        pago = row.get('Pago', None)
        if pd.notna(pago) and float(pago) == 25:
            color = 'green'; icono = 'ok-sign'; tip = 'Dentro cuadrante ($25)'
        elif pd.notna(pago) and float(pago) == 75:
            color = 'red'; icono = 'remove-sign'; tip = 'Fuera cuadrante ($75)'
        else:
            color = 'gray'; icono = 'question-sign'; tip = 'Sin clasificación'

        fecha_val = row.get('Fecha de llenar', pd.NaT)
        fecha_str = fecha_val.strftime('%d/%m/%Y %H:%M') if pd.notna(fecha_val) else 'N/A'

        popup_html = f"""
        <div style='width:260px;'>
            <h4 style='margin:0 0 6px 0;'>Detalle de Entrega</h4>
            <p style='margin:0;'><b>Colaborador:</b> {row.get('Empleado', 'N/A')}</p>
            <p style='margin:0;'><b>Cliente:</b> {row.get('Nombre del cliente (usuario/codigo)', 'N/A')}</p>
            <p style='margin:0;'><b>Pago:</b> ${row.get('Pago', 'N/A')}</p>
            <p style='margin:0;'><b>Fecha:</b> {fecha_str}</p>
            <p style='margin:0;'><b>Dirección:</b> {str(row.get('Dirección de envío', 'N/A'))[:60]}...</p>
        </div>
        """

        folium.Marker(
            location=[row['Latitud'], row['Longitud']],
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=tip,
            icon=folium.Icon(color=color, icon=icono, prefix='glyphicon'),
        ).add_to(m)

    # Leyenda simple (HTML)
    legend_html = """
    <div style="
        position: fixed;
        bottom: 30px; left: 30px;
        z-index: 9999; background: white;
        padding: 8px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 13px;">
      <b>Leyenda</b><br>
      <span style="display:inline-block;width:10px;height:10px;background:green;margin-right:6px;"></span> $25 (dentro cuadrante)<br>
      <span style="display:inline-block;width:10px;height:10px;background:red;margin-right:6px;"></span> $75 (fuera cuadrante)
    </div>
    """
    m.get_root().html.add_child(Element(legend_html))

    folium.LayerControl().add_to(m)
    return m


# ==============================
# PDF – solo tabla + subtotales diarios + total general
# ==============================
class ReportPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Reporte de Mensajería - IDEMEFA', 0, 1, 'C')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')


def _add_table_header(pdf: ReportPDF, headers, widths):
    pdf.set_font('Arial', 'B', 8)
    for h, w in zip(headers, widths):
        h_txt = (h[:28] + '...') if len(h) > 31 else h
        pdf.cell(w, 8, h_txt, 1)
    pdf.ln()


def _add_row(pdf: ReportPDF, values, widths):
    pdf.set_font('Arial', '', 7)
    for v, w in zip(values, widths):
        txt = str(v) if v is not None else ''
        if len(txt) > 45:
            txt = txt[:45] + '...'
        pdf.cell(w, 7, txt, 1)
    pdf.ln()


def generar_pdf(df_filtrado: pd.DataFrame, fecha_inicio: datetime, fecha_fin: datetime, colaborador: str):
    pdf = ReportPDF()
    pdf.add_page()

    # Encabezado de reporte
    pdf.set_font('Arial', 'B', 13)
    pdf.cell(0, 10, 'REPORTE DETALLADO (Solo tabla)', 0, 1, 'C')
    pdf.ln(2)

    pdf.set_font('Arial', '', 10)
    periodo_txt = f"Período: {fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')}"
    colab_txt = f"Colaborador: {'Todos' if colaborador == 'Total' else colaborador}"
    gen_txt = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    for line in (periodo_txt, colab_txt, gen_txt):
        pdf.cell(0, 7, line, 0, 1)
    pdf.ln(4)

    # Asegurar columnas
    cols_presentes = [c for c in COLUMNAS_TABLA if c in df_filtrado.columns]
    # Ajustes de ancho (suma aprox 190)
    widths_map = {
        'Empleado': 25,
        'Tipo': 16,
        'Dirección de envío': 48,
        'Fecha de llenar': 26,
        'Nombre del cliente (usuario/codigo)': 35,
        'Nombre de quien recibe (maria/secretaria, juan/asistente, miguel ruiz/doctor)': 40,
        'Pago': 16,
    }
    widths = [widths_map.get(c, 28) for c in cols_presentes]

    # Ordenar por fecha para subtotales
    if 'Fecha de llenar' in df_filtrado.columns:
        df_filtrado = df_filtrado.sort_values('Fecha de llenar')

    # Subtotales por día
    if 'Fecha de llenar' in df_filtrado.columns:
        df_filtrado['__FechaD__'] = df_filtrado['Fecha de llenar'].dt.date
    else:
        df_filtrado['__FechaD__'] = None

    total_general = 0.0
    total_checkins = 0

    for fecha_dia, df_dia in df_filtrado.groupby('__FechaD__'):
        # Título de día
        if isinstance(fecha_dia, date):
            titulo_dia = fecha_dia.strftime('%d/%m/%Y')
        else:
            try:
                titulo_dia = pd.to_datetime(fecha_dia).strftime('%d/%m/%Y')
            except Exception:
                titulo_dia = 'Sin fecha'

        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, f"Día: {titulo_dia}", 0, 1)

        _add_table_header(pdf, cols_presentes, widths)

        for _, r in df_dia.iterrows():
            vals = []
            for c in cols_presentes:
                val = r.get(c, '')
                if c == 'Fecha de llenar' and pd.notna(val):
                    val = pd.to_datetime(val).strftime('%d/%m/%Y %H:%M')
                vals.append(val)
            _add_row(pdf, vals, widths)

            # salto de página si es necesario
            if pdf.get_y() > 265:
                pdf.add_page()
                _add_table_header(pdf, cols_presentes, widths)

        # Subtotal del día
        monto_dia = df_dia['Pago'].sum() if 'Pago' in df_dia.columns else 0
        checkins_dia = len(df_dia)
        total_general += float(monto_dia or 0)
        total_checkins += int(checkins_dia)

        pdf.set_font('Arial', 'B', 9)
        pdf.cell(sum(widths[:-2]), 8, 'Subtotal del día', 1)
        pdf.cell(widths[-2], 8, str(checkins_dia), 1)
        pdf.cell(widths[-1], 8, f"${monto_dia:,.2f}", 1)
        pdf.ln(10)

    # Totales generales
    pdf.ln(2)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 8, 'TOTAL GENERAL DEL PERIODO', 0, 1)

    pdf.set_font('Arial', 'B', 10)
    pdf.cell(60, 8, 'Check-ins', 1)
    pdf.cell(60, 8, 'Monto total', 1)
    pdf.ln()

    pdf.set_font('Arial', '', 10)
    pdf.cell(60, 8, str(total_checkins), 1)
    pdf.cell(60, 8, f"${total_general:,.2f}", 1)

    return pdf


# ==============================
# APP (una sola pestaña)
# ==============================
st.set_page_config(page_title="Reporte Mensajería", page_icon="🚚", layout="wide")
st.title("🚚 Reporte de Mensajería – IDEMEFA")
st.caption("Filtro por empleado y rango de fechas → mapa con marcadores y polígono de zona → tabla filtrada → subtotales diarios y total → descarga en PDF (solo tabla)")
st.markdown("---")

# Cargar datos
with st.spinner("Cargando datos..."):
    df = cargar_datos(SHEET_URL)

if df.empty:
    st.stop()

# Sidebar – filtros
st.sidebar.header("Filtros")

# Rango de fechas
if 'Fecha de llenar' in df.columns and df['Fecha de llenar'].notna().any():
    fecha_min = pd.to_datetime(df['Fecha de llenar'].min())
    fecha_max = pd.to_datetime(df['Fecha de llenar'].max())
else:
    fecha_min = datetime.now() - timedelta(days=30)
    fecha_max = datetime.now()

rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(fecha_min.date(), fecha_max.date()),
    min_value=min(fecha_min.date(), fecha_max.date()),
    max_value=max(fecha_min.date(), fecha_max.date()),
)

# Colaborador
colaboradores = ['Total']
if 'Empleado' in df.columns:
    colaboradores += sorted([x for x in df['Empleado'].dropna().unique().tolist() if str(x).strip() != ''])
colab_sel = st.sidebar.selectbox("Colaborador", colaboradores)

# Aplicar filtros
if isinstance(rango, (list, tuple)) and len(rango) == 2:
    fecha_inicio = pd.to_datetime(rango[0])
    fecha_fin = pd.to_datetime(rango[1]) + timedelta(days=1) - timedelta(seconds=1)
else:
    fecha_inicio = fecha_min
    fecha_fin = fecha_max

mask = pd.Series([True] * len(df))
if 'Fecha de llenar' in df.columns:
    mask &= (df['Fecha de llenar'] >= fecha_inicio) & (df['Fecha de llenar'] <= fecha_fin)
if colab_sel != 'Total' and 'Empleado' in df.columns:
    mask &= (df['Empleado'] == colab_sel)

df_filtrado = df.loc[mask].copy()

# ==============================
# Métricas rápidas
# ==============================
st.subheader("📊 Resumen")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total entregas", len(df_filtrado))
with c2:
    st.metric("Monto total", f"${(df_filtrado['Pago'].sum() if 'Pago' in df_filtrado.columns else 0):,.2f}")
with c3:
    v25 = int((df_filtrado['Pago'] == 25).sum() if 'Pago' in df_filtrado.columns else 0)
    st.metric("Entregas $25", v25)
with c4:
    v75 = int((df_filtrado['Pago'] == 75).sum() if 'Pago' in df_filtrado.columns else 0)
    st.metric("Entregas $75", v75)

# ==============================
# Mapa
# ==============================
st.subheader("🗺️ Mapa de entregas")
m = crear_mapa(df_filtrado)
if m is not None:
    st_folium(m, width=1100, height=520)
else:
    st.info("No hay coordenadas válidas para mostrar con los filtros actuales.")

# ==============================
# Tabla + subtotales por día (en pantalla)
# ==============================
st.subheader("📋 Detalle filtrado")
cols_disp = [c for c in COLUMNAS_TABLA if c in df_filtrado.columns]

if cols_disp:
    df_vis = df_filtrado[cols_disp].copy()
    # Formato de fecha visible
    if 'Fecha de llenar' in df_vis.columns:
        df_vis['Fecha de llenar'] = pd.to_datetime(df_vis['Fecha de llenar'], errors='coerce')
    st.dataframe(df_vis, use_container_width=True)

    # Subtotales por día
    if 'Fecha de llenar' in df_filtrado.columns:
        st.markdown("#### Subtotales por día (según filtros)")
        tmp = df_filtrado.copy()
        tmp['__FechaD__'] = tmp['Fecha de llenar'].dt.date
        resumen = tmp.groupby('__FechaD__').agg(
            Checkins=('Empleado', 'count'),
            Monto_Total=('Pago', 'sum')
        ).reset_index().rename(columns={'__FechaD__': 'Fecha'})
        resumen['Fecha'] = pd.to_datetime(resumen['Fecha'])
        resumen = resumen.sort_values('Fecha')
        st.dataframe(resumen, use_container_width=True)

        total_checkins = int(resumen['Checkins'].sum()) if not resumen.empty else 0
        total_monto = float(resumen['Monto_Total'].sum()) if not resumen.empty else 0.0
        st.markdown(f"**Total general del período:** {total_checkins} check-ins | ${total_monto:,.2f}")

    # ==============================
    # PDF – solo tabla con subtotales y total
    # ==============================
    st.subheader("📄 Descargar PDF (solo tabla)")
    if st.button("Generar PDF", type="primary"):
        with st.spinner("Generando PDF..."):
            try:
                pdf = generar_pdf(
                    df_filtrado=df_filtrado[cols_disp].copy(),
                    fecha_inicio=pd.to_datetime(fecha_inicio),
                    fecha_fin=pd.to_datetime(fecha_fin),
                    colaborador=colab_sel,
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    pdf.output(tmp.name)
                    tmp.flush()
                    with open(tmp.name, 'rb') as f:
                        data = f.read()
                st.download_button(
                    label="⬇️ Descargar PDF",
                    data=data,
                    file_name=f"reporte_mensajeria_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    type="primary",
                )
                os.unlink(tmp.name)
                st.success("PDF generado correctamente.")
            except Exception as e:
                st.error(f"Error generando PDF: {e}")
else:
    st.info("No se encontraron las columnas requeridas en los datos para mostrar la tabla.")
