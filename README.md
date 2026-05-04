# AudioEq - Public Transport Audio Equalizer & Normalizer

Proyecto de ecualizador de audio y normalizador de volumen para anuncios en transporte público (Metrobús CDMX).

## 🎯 Objetivo

Normalizar audio de anuncios que se transmiten en autobuses mediante Raspberry Pi, garantizando:
- ✅ **Volumen consistente** (-16 LUFS estándar) sin ajustes manuales
- ✅ **Calidad superior** mediante procesamiento offline (no real-time)
- ✅ **Compresión adaptiva** para ambientes ruidosos
- ✅ **Automático** - Procesa diariamente archivos descargados

## 🏗️ Arquitectura

```
Servidor Central (descarga media)
    ↓
Raspberry Pi 4
    ↓
[1] Análisis de Loudness
[2] Compresión Multi-Stage (3 etapas)
[3] Normalización LUFS (-16 LUFS)
[4] Validación de Calidad
    ↓
Almacenamiento de audio procesado
    ↓
Reproducción en fuentes de audio del autobús
```

## 📊 Características Principales

### Normalización de Audio
- **LUFS Normalization** (Loudness Units - estándar de broadcast)
- **Peak Normalization** (normalización por amplitud pico)
- **RMS Normalization** (normalización por nivel RMS)
- Todos los métodos con prevención automática de clipping

### Compresión Dinámica
- **MultiStageCompressor** (3 etapas - RECOMENDADO para transporte):
  1. Limiter rápido (-3dB, ratio 10:1) - Previene picos
  2. Compresor principal (-18dB, ratio 4:1) - Suaviza volumen
  3. Limiter final (-0.5dB, ratio 8:1) - Seguridad
  
- **SoftKneeCompressor** - Compresión natural y suave
- **DynamicRangeCompressor** - Compresor estándar configurable

### Pipeline Completo
- Carga MP3, WAV, FLAC, M4A
- Análisis de loudness antes/después
- Procesamiento automático batch
- Eliminación de archivos originales
- Reportes JSON detallados

## 🚀 Instalación

### Requisitos
- Python 3.8+
- pip (gestor de paquetes Python)

### Pasos

1. **Clonar repositorio**
```bash
git clone https://github.com/DGlezTest/AudioEq.git
cd AudioEq
```

2. **Instalar dependencias**
```bash
pip install -r requirements.txt
```

3. **Verificar instalación**
```bash
python -c "from src.audio_processor import AudioProcessor; print('✓ AudioEq ready!')"
```

## 📝 Uso

### Opción 1: Procesar un archivo individual

```python
from src.audio_processor import AudioProcessor

processor = AudioProcessor('config/settings.yaml')

result = processor.process_file(
    input_file='anuncio.mp3',
    output_file='anuncio_procesado.wav',
    apply_compression=True,
    apply_normalization=True,
)

print(f"Original LUFS: {result['metadata']['analysis_before']['lufs']:.2f}")
print(f"Final LUFS: {result['metadata']['analysis_after']['lufs']:.2f}")
```

### Opción 2: Procesar batch diario (RECOMENDADO)

```bash
# Procesar todos los archivos del día
python scripts/process_daily.py \
  --input-dir ./audios_descargados \
  --output-dir ./audios_procesados \
  --delete-original \
  --report report.json
```

Salida esperada:
```
======================================================================
DAILY AUDIO PROCESSING - 2026-05-04 10:00:00
======================================================================
[1/15] Processing: anuncio_001.mp3
✓ Processing complete: anuncio_001.mp3 → anuncio_001.wav

[2/15] Processing: anuncio_002.mp3
✓ Processing complete: anuncio_002.mp3 → anuncio_002.wav

...

======================================================================
PROCESSING SUMMARY
======================================================================
Total files: 15
Successfully processed: 15
Failed: 0
Output directory: ./audios_procesados
All files normalized to: -16 LUFS (transport standard)
======================================================================
```

### Opción 3: Analizar y verificar calidad

```bash
# Verificar que todos están a -16 LUFS
python scripts/analyze_audio.py ./audios_procesados

# Salida:
# ======================================================================
# LOUDNESS ANALYSIS REPORT
# ======================================================================
# Directory: ./audios_procesados
# Total files: 15
# Standard: TRANSPORT (-16 LUFS)
# 
# STATISTICS:
#   Files analyzed: 15
#   Mean LUFS: -16.02
#   Min LUFS: -15.8
#   Max LUFS: -16.1
#   Std Dev: ±0.12
# 
# ✓ ALL FILES WITHIN TOLERANCE! (±1.0 LUFS)
```

## ⚙️ Configuración

El archivo `config/settings.yaml` controla todo:

```yaml
normalization:
  target_lufs: -16.0        # Estándar transporte (-16 LUFS)
  method: lufs              # Usar LUFS (recomendado)
  tolerance_db: 1.0         # ±1 dB de tolerancia

compression:
  enabled: true             # ACTIVAR COMPRESIÓN
  type: multiStage          # 3-etapas (ideal para ruido extremo)

processing:
  delete_originals: true    # Eliminar después de procesar
  output_format: wav        # Formato sin pérdida
  headroom_db: 1.0          # Margen de seguridad
```

## 🔧 Para Raspberry Pi

### Instalación Específica para Pi

```bash
# En Raspberry Pi, instalar dependencias del sistema
sudo apt-get install -y python3-dev libffi-dev libssl-dev
sudo apt-get install -y libsndfile1 libsndfile1-dev

# Luego instalar AudioEq
git clone https://github.com/DGlezTest/AudioEq.git
cd AudioEq
pip install -r requirements.txt
```

### Automatizar con Cron

Procesar automáticamente cada día a las 10:00 AM:

```bash
# Editar crontab
crontab -e

# Agregar esta línea:
0 10 * * * cd /path/to/AudioEq && python scripts/process_daily.py --delete-original --report /tmp/daily_report.json >> /var/log/audio_processing.log 2>&1
```

### Estructura de Directorios Recomendada

```bash
mkdir -p ~/AudioEq/audios_descargados
mkdir -p ~/AudioEq/audios_procesados
mkdir -p ~/AudioEq/logs
mkdir -p ~/AudioEq/reports

# Logs
tail -f ~/AudioEq/audio_processing.log
```

## 📊 Ejemplos de Antes/Después

### Archivo 1: Muy fuerte (-8.5 LUFS)
```
ANTES:  -8.5 LUFS | Peak: -0.2 dB  ✗ Clipping
         ↓
[Compresión] → [Normalización LUFS]
         ↓
DESPUÉS: -16.0 LUFS | Peak: -6.0 dB ✓ Seguro
```

### Archivo 2: Muy débil (-24 LUFS)
```
ANTES:   -24.0 LUFS | Peak: -20 dB  ✗ Inaudible
         ↓
[Compresión] → [Normalización LUFS]
         ↓
DESPUÉS: -16.0 LUFS | Peak: -6.0 dB ✓ Claro
```

### Archivo 3: Dinámico (variable -10 a -22 LUFS)
```
ANTES:   Variable -10 to -22 LUFS   ✗ Inconsistente
         ↓
[Multi-Stage Compression] → [Normalización LUFS]
         ↓
DESPUÉS: -16.0 LUFS (consistente)  ✓ Perfecto
```

## 🎯 Próximos Pasos

- [ ] Crear perfiles específicos por marca de equipamiento (Audiobahn, Pioneer, etc.)
- [ ] Agregar ecualizador gráfico de 5-31 bandas
- [ ] Implementar dashboard web para monitoreo
- [ ] Agregar calibración interactiva por unidad de transporte
- [ ] Machine Learning para optimización automática
- [ ] Soporte para múltiples idiomas en anuncios

## 📚 Estructura del Proyecto

```
AudioEq/
├── src/
│   ├── audio_processor.py      # Pipeline principal
│   ├── normalizer.py            # Normalización LUFS/Peak/RMS
│   ├── compressor.py            # Compresores dinámicos
│   ├── spectrum_analyzer.py     # Análisis de espectro (próximo)
│   └── equalizer.py             # EQ de 5 bandas (próximo)
├── config/
│   ├── settings.yaml            # Configuración global
│   └── profiles/
│       └── generic_profile.json # Perfil de equipo base
├── scripts/
│   ├── process_daily.py         # Procesamiento automático diario
│   ├── analyze_audio.py         # Análisis y verificación
│   └── calibration_tool.py      # Herramienta de calibración (próximo)
├── tests/
│   └── test_audio.py
├── docs/
│   └── INSTALLATION.md          # Guía de instalación
├── requirements.txt
└── README.md
```

## 🐛 Troubleshooting

### Error: "pyloudnorm not found"
```bash
pip install pyloudnorm
```

### Error: "librosa not found"
```bash
pip install librosa
```

### Archivos procesados, pero LUFS aún no está a -16
1. Revisar `config/settings.yaml` - asegurar `target_lufs: -16.0`
2. Ejecutar análisis: `python scripts/analyze_audio.py ./audios_procesados`
3. Revisar logs: `tail -f audio_processing.log`

### Compresión muy agresiva
Cambiar en `config/settings.yaml`:
```yaml
compression:
  type: softKnee  # En lugar de multiStage (más suave)
```

## 📞 Soporte

Para reportar bugs o sugerencias, abre un issue en: https://github.com/DGlezTest/AudioEq/issues

## 📄 Licencia

MIT License - Libre para uso personal y comercial

## 👨‍💻 Contribuciones

Las contribuciones son bienvenidas. Por favor:
1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

**Hecho para mejorar la experiencia de audio en transporte público 🎵🚌**
