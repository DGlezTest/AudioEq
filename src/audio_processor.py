"""
Main Audio Processing Pipeline
Orchestrates normalization, compression, equalization, and file management
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
import numpy as np
import librosa
import soundfile as sf
import yaml

from src.normalizer import AudioNormalizer, CompressiveNormalizer
from src.compressor import (
    DynamicRangeCompressor, 
    MultiStageCompressor, 
    SoftKneeCompressor
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Main audio processing pipeline for public transport announcements.
    
    Pipeline steps:
    1. Load audio file
    2. Analyze loudness characteristics
    3. Apply compression (optional)
    4. Apply normalization (LUFS-based)
    5. Apply equalization (optional)
    6. Save processed audio
    """
    
    def __init__(self, config_file: str = 'config/settings.yaml'):
        """
        Initialize audio processor.
        
        Args:
            config_file: Path to YAML configuration file
        """
        self.config = self._load_config(config_file)
        
        # Initialize components
        self.normalizer = AudioNormalizer(
            target_lufs=self.config.get('normalization', {}).get('target_lufs', -16.0),
            standard='transport'
        )
        
        self.compressor = self._init_compressor()
        
        logger.info("AudioProcessor initialized")
    
    def _load_config(self, config_file: str) -> Dict:
        """Load YAML configuration file."""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f) or {}
            logger.info(f"Loaded config: {config_file}")
            return config
        except Exception as e:
            logger.warning(f"Could not load config {config_file}: {e}, using defaults")
            return {
                'normalization': {'target_lufs': -16.0, 'method': 'lufs'},
                'compression': {'enabled': True, 'type': 'multiStage'},
            }
    
    def _init_compressor(self):
        """Initialize compressor based on config."""
        comp_config = self.config.get('compression', {})
        comp_type = comp_config.get('type', 'multiStage')
        
        if not comp_config.get('enabled', True):
            logger.info("Compression disabled in config")
            return None
        
        if comp_type == 'multiStage':
            logger.info("Using MultiStageCompressor")
            return MultiStageCompressor()
        elif comp_type == 'softKnee':
            logger.info("Using SoftKneeCompressor")
            return SoftKneeCompressor(
                threshold_db=comp_config.get('threshold_db', -20.0),
                ratio=comp_config.get('ratio', 4.0),
                knee_width_db=comp_config.get('knee_width_db', 6.0),
            )
        else:  # standard
            logger.info("Using DynamicRangeCompressor")
            return DynamicRangeCompressor(
                threshold_db=comp_config.get('threshold_db', -20.0),
                ratio=comp_config.get('ratio', 4.0),
            )
    
    def analyze_file(self, file_path: str) -> Dict:
        """
        Analyze audio file without processing.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dictionary with analysis results
        """
        try:
            audio, sr = librosa.load(file_path, sr=None, mono=False)
            
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=0)
            
            logger.info(f"Analyzing: {file_path} ({sr}Hz, {audio.shape})")
            
            analysis = self.normalizer.analyze_loudness(audio, sr)
            analysis['file_path'] = file_path
            analysis['sample_rate'] = sr
            analysis['channels'] = audio.shape[0] if audio.ndim > 1 else 1
            analysis['duration_seconds'] = len(audio[0] if audio.ndim > 1 else audio) / sr
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")
            return {'error': str(e)}
    
    def process_file(self, 
                    input_file: str, 
                    output_file: str,
                    profile: Optional[str] = None,
                    apply_compression: bool = True,
                    apply_normalization: bool = True,
                    delete_original: bool = False) -> Dict:
        """
        Process a single audio file through complete pipeline.
        
        Args:
            input_file: Path to input audio file
            output_file: Path to output audio file
            profile: Optional path to equipment profile JSON
            apply_compression: Whether to apply dynamic range compression
            apply_normalization: Whether to apply LUFS normalization
            delete_original: Whether to delete original file after processing
            
        Returns:
            Dictionary with processing results and metadata
        """
        results = {
            'success': False,
            'input_file': input_file,
            'output_file': output_file,
            'steps_executed': [],
            'metadata': {},
            'errors': [],
        }
        
        try:
            # 1. Load audio
            logger.info(f"Loading: {input_file}")
            audio, sr = librosa.load(input_file, sr=None, mono=False)
            
            # Ensure stereo
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=0)
            
            results['metadata']['original_sample_rate'] = sr
            results['metadata']['channels'] = audio.shape[0]
            results['steps_executed'].append('load')
            
            # 2. Analyze original
            analysis_before = self.normalizer.analyze_loudness(audio, sr)
            results['metadata']['analysis_before'] = analysis_before
            logger.info(f"Original LUFS: {analysis_before['lufs']:.2f}")
            
            # 3. Apply compression if enabled
            if apply_compression and self.compressor:
                logger.info("Applying compression...")
                audio, comp_meta = self.compressor.compress(audio, sr)
                results['metadata']['compression'] = comp_meta
                results['steps_executed'].append('compression')
            
            # 4. Apply normalization
            if apply_normalization:
                logger.info("Applying normalization...")
                norm_method = self.config.get('normalization', {}).get('method', 'lufs')
                audio, norm_meta = self.normalizer.normalize_lufs(audio, sr)
                results['metadata']['normalization'] = norm_meta
                results['steps_executed'].append('normalization')
            
            # 5. Analyze after processing
            analysis_after = self.normalizer.analyze_loudness(audio, sr)
            results['metadata']['analysis_after'] = analysis_after
            logger.info(f"Final LUFS: {analysis_after['lufs']:.2f}")
            
            # 6. Save output
            os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
            sf.write(output_file, audio.T if audio.ndim > 1 else audio, sr)
            logger.info(f"Saved: {output_file}")
            results['steps_executed'].append('save')
            
            # 7. Delete original if requested
            if delete_original and os.path.exists(input_file):
                os.remove(input_file)
                logger.info(f"Deleted original: {input_file}")
                results['steps_executed'].append('delete_original')
            
            results['success'] = True
            logger.info(f"✓ Processing complete: {input_file} → {output_file}")
            
        except Exception as e:
            logger.error(f"Error processing {input_file}: {e}")
            results['errors'].append(str(e))
        
        return results
    
    def batch_process(self,
                     input_dir: str,
                     output_dir: str,
                     profile: Optional[str] = None,
                     file_pattern: str = '*.mp3',
                     delete_originals: bool = False) -> Dict:
        """
        Process multiple audio files in batch.
        
        Args:
            input_dir: Directory containing input files
            output_dir: Directory for output files
            profile: Optional equipment profile
            file_pattern: File pattern to match (e.g., '*.mp3')
            delete_originals: Whether to delete originals after processing
            
        Returns:
            Dictionary with batch results
        """
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Find matching files
        files = sorted(input_path.glob(file_pattern))
        logger.info(f"Found {len(files)} files in {input_dir}")
        
        results = {
            'total_files': len(files),
            'processed_files': 0,
            'failed_files': 0,
            'skipped_files': 0,
            'details': [],
        }
        
        for i, input_file in enumerate(files, 1):
            logger.info(f"\n[{i}/{len(files)}] Processing: {input_file.name}")
            
            # Generate output filename
            output_file = output_path / f"processed_{input_file.stem}.wav"
            
            # Process
            result = self.process_file(
                str(input_file),
                str(output_file),
                profile=profile,
                delete_original=delete_originals
            )
            
            results['details'].append(result)
            
            if result['success']:
                results['processed_files'] += 1
            else:
                results['failed_files'] += 1
        
        logger.info(f"\n\nBatch Summary:")
        logger.info(f"  Processed: {results['processed_files']}")
        logger.info(f"  Failed: {results['failed_files']}")
        logger.info(f"  Output dir: {output_dir}")
        
        return results


# Example usage functions
def example_single_file():
    """Example: Process a single file."""
    processor = AudioProcessor('config/settings.yaml')
    
    result = processor.process_file(
        input_file='sample_audio.mp3',
        output_file='output/sample_audio_processed.wav',
        apply_compression=True,
        apply_normalization=True,
    )
    
    print(json.dumps(result, indent=2))


def example_batch_processing():
    """Example: Batch process directory."""
    processor = AudioProcessor('config/settings.yaml')
    
    results = processor.batch_process(
        input_dir='./audios_descargados',
        output_dir='./audios_procesados',
        file_pattern='*.mp3',
        delete_originals=True,
    )
    
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    # Uncomment to test
    # example_single_file()
    # example_batch_processing()
    pass
