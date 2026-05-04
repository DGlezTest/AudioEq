"""
Audio Normalization Module for Public Transport
Ensures consistent loudness across all audio files regardless of source
"""

import numpy as np
import librosa
import soundfile as sf
import pyloudnorm
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class AudioNormalizer:
    """
    Normalizes audio to broadcast standards for public transport.
    
    Key normalization strategies:
    1. LUFS Normalization (Loudness Units relative to Full Scale)
    2. Peak normalization with headroom
    3. RMS-based normalization as fallback
    """
    
    # Broadcast standards for different use cases
    STANDARDS = {
        'broadcast': -18.0,      # EBU R128 broadcast standard
        'streaming': -14.0,       # Spotify/Apple Music standard
        'transport': -16.0,       # Public transport (balanced for noisy environments)
        'podcast': -16.0,         # Podcast standard
    }
    
    # Safety margins to prevent clipping
    HEADROOM_DB = 1.0  # 1dB safety margin
    
    def __init__(self, target_lufs: float = -16.0, standard: str = 'transport'):
        """
        Initialize normalizer.
        
        Args:
            target_lufs: Target loudness in LUFS (-16.0 for public transport)
            standard: One of 'broadcast', 'streaming', 'transport', 'podcast'
        """
        self.target_lufs = target_lufs if target_lufs else self.STANDARDS.get(standard, -16.0)
        self.meter = pyloudnorm.Meter(44100)  # Will be updated per file
        
        logger.info(f"AudioNormalizer initialized: {self.target_lufs} LUFS (Standard: {standard})")
    
    def normalize_lufs(self, audio: np.ndarray, sr: int) -> Tuple[np.ndarray, Dict]:
        """
        Normalize audio using LUFS (Loudness Units relative to Full Scale).
        
        This is the BEST method for consistent loudness across different sources.
        
        Args:
            audio: Audio signal (mono or stereo)
            sr: Sample rate
            
        Returns:
            Tuple of (normalized_audio, metadata)
        """
        try:
            # Update meter for current sample rate
            self.meter = pyloudnorm.Meter(sr)
            
            # Ensure stereo for LUFS calculation
            if audio.ndim == 1:
                audio_stereo = np.stack([audio, audio], axis=0)
            else:
                audio_stereo = audio
            
            # Measure current loudness
            current_lufs = self.meter.integrated_loudness(audio_stereo)
            
            # Handle edge cases
            if current_lufs is None or np.isnan(current_lufs):
                logger.warning("Could not measure LUFS, using peak normalization instead")
                return self.normalize_peak(audio)
            
            # Calculate required gain
            loudness_diff = self.target_lufs - current_lufs
            
            # Apply gain with headroom
            gain_linear = 10 ** ((loudness_diff - self.HEADROOM_DB) / 20.0)
            normalized_audio = audio * gain_linear
            
            # Prevent clipping
            max_val = np.max(np.abs(normalized_audio))
            if max_val > 1.0:
                normalized_audio = normalized_audio / max_val
                logger.warning(f"Clipping detected, reduced by {20 * np.log10(max_val):.2f}dB")
            
            metadata = {
                'method': 'LUFS',
                'original_lufs': float(current_lufs),
                'target_lufs': self.target_lufs,
                'gain_applied_db': float(loudness_diff - self.HEADROOM_DB),
                'headroom_db': self.HEADROOM_DB,
                'clipping_prevented': max_val > 1.0,
            }
            
            logger.info(f"LUFS Normalization: {current_lufs:.2f} → {self.target_lufs} LUFS "
                       f"(Gain: {loudness_diff - self.HEADROOM_DB:.2f}dB)")
            
            return normalized_audio, metadata
            
        except Exception as e:
            logger.error(f"LUFS normalization failed: {e}, falling back to peak")
            return self.normalize_peak(audio)
    
    def normalize_peak(self, audio: np.ndarray) -> Tuple[np.ndarray, Dict]:
        """
        Normalize audio by peak value (simpler, more predictable).
        
        Normalizes peak to -1dB (0.89 linear) to prevent clipping.
        
        Args:
            audio: Audio signal
            
        Returns:
            Tuple of (normalized_audio, metadata)
        """
        # Target peak level (-1dB = 0.89 linear)
        target_peak_linear = 10 ** (-1.0 / 20.0)
        
        current_peak = np.max(np.abs(audio))
        
        if current_peak == 0:
            logger.warning("Audio is silent!")
            return audio, {'method': 'Peak', 'warning': 'Silent audio'}
        
        # Calculate gain
        gain_linear = target_peak_linear / current_peak
        gain_db = 20 * np.log10(gain_linear)
        
        normalized_audio = audio * gain_linear
        
        metadata = {
            'method': 'Peak',
            'original_peak_db': float(20 * np.log10(current_peak)),
            'target_peak_db': -1.0,
            'gain_applied_db': float(gain_db),
        }
        
        logger.info(f"Peak Normalization: {20 * np.log10(current_peak):.2f}dB → -1.0dB "
                   f"(Gain: {gain_db:.2f}dB)")
        
        return normalized_audio, metadata
    
    def normalize_rms(self, audio: np.ndarray) -> Tuple[np.ndarray, Dict]:
        """
        Normalize audio by RMS (Root Mean Square) level.
        
        More conservative than peak normalization, better for dynamic content.
        
        Args:
            audio: Audio signal
            
        Returns:
            Tuple of (normalized_audio, metadata)
        """
        # RMS target: -10dB (0.316 linear)
        target_rms_linear = 10 ** (-10.0 / 20.0)
        
        current_rms = np.sqrt(np.mean(audio ** 2))
        
        if current_rms == 0:
            logger.warning("Audio is silent!")
            return audio, {'method': 'RMS', 'warning': 'Silent audio'}
        
        # Calculate gain
        gain_linear = target_rms_linear / current_rms
        gain_db = 20 * np.log10(gain_linear)
        
        normalized_audio = audio * gain_linear
        
        # Apply headroom to prevent clipping
        max_val = np.max(np.abs(normalized_audio))
        if max_val > 0.95:
            normalized_audio = normalized_audio * (0.95 / max_val)
            logger.warning(f"Clipping prevented by reducing {20 * np.log10(0.95 / max_val):.2f}dB")
        
        metadata = {
            'method': 'RMS',
            'original_rms_db': float(20 * np.log10(current_rms)),
            'target_rms_db': -10.0,
            'gain_applied_db': float(gain_db),
        }
        
        logger.info(f"RMS Normalization: {20 * np.log10(current_rms):.2f}dB → -10.0dB "
                   f"(Gain: {gain_db:.2f}dB)")
        
        return normalized_audio, metadata
    
    def analyze_loudness(self, audio: np.ndarray, sr: int) -> Dict:
        """
        Analyze loudness characteristics without modifying audio.
        
        Args:
            audio: Audio signal
            sr: Sample rate
            
        Returns:
            Dictionary with loudness metrics
        """
        self.meter = pyloudnorm.Meter(sr)
        
        # Prepare for LUFS (needs stereo)
        if audio.ndim == 1:
            audio_stereo = np.stack([audio, audio], axis=0)
        else:
            audio_stereo = audio
        
        current_lufs = self.meter.integrated_loudness(audio_stereo)
        
        # Calculate other metrics
        peak_db = 20 * np.log10(np.max(np.abs(audio)) + 1e-10)
        rms_db = 20 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-10)
        crest_factor = np.max(np.abs(audio)) / np.sqrt(np.mean(audio ** 2) + 1e-10)
        
        analysis = {
            'lufs': float(current_lufs) if current_lufs else None,
            'peak_db': float(peak_db),
            'rms_db': float(rms_db),
            'crest_factor': float(crest_factor),
            'crest_factor_db': float(20 * np.log10(crest_factor)),
            'target_lufs': self.target_lufs,
            'loudness_difference_db': float(self.target_lufs - current_lufs) if current_lufs else None,
        }
        
        return analysis
    
    def process_file(self, input_path: str, output_path: str, 
                    method: str = 'lufs') -> Dict:
        """
        Normalize an audio file and save to disk.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to output audio file
            method: 'lufs', 'peak', or 'rms'
            
        Returns:
            Dictionary with processing results
        """
        try:
            # Load audio
            audio, sr = librosa.load(input_path, sr=None, mono=False)
            
            # Ensure stereo for consistency
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=0)
            
            logger.info(f"Loaded: {input_path} ({sr}Hz, {audio.shape})")
            
            # Choose normalization method
            if method.lower() == 'lufs':
                normalized_audio, norm_meta = self.normalize_lufs(audio, sr)
            elif method.lower() == 'peak':
                normalized_audio, norm_meta = self.normalize_peak(audio)
            elif method.lower() == 'rms':
                normalized_audio, norm_meta = self.normalize_rms(audio)
            else:
                raise ValueError(f"Unknown normalization method: {method}")
            
            # Get analysis
            analysis = self.analyze_loudness(normalized_audio, sr)
            
            # Save
            sf.write(output_path, normalized_audio.T if normalized_audio.ndim > 1 else normalized_audio, sr)
            logger.info(f"Saved: {output_path}")
            
            return {
                'success': True,
                'input_file': input_path,
                'output_file': output_path,
                'sample_rate': sr,
                'normalization_method': method,
                'normalization_metadata': norm_meta,
                'analysis': analysis,
            }
            
        except Exception as e:
            logger.error(f"Error processing {input_path}: {e}")
            return {'success': False, 'error': str(e)}


class CompressiveNormalizer:
    """
    Advanced normalizer using dynamic range compression.
    
    Better for highly variable audio (typical in public transport).
    """
    
    def __init__(self, threshold_db: float = -20.0, ratio: float = 4.0):
        """
        Initialize compressive normalizer.
        
        Args:
            threshold_db: Compression threshold
            ratio: Compression ratio (higher = more aggressive)
        """
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.attack_ms = 10
        self.release_ms = 100
        
        logger.info(f"CompressiveNormalizer: threshold={threshold_db}dB, ratio={ratio}:1")
    
    def compress(self, audio: np.ndarray, sr: int) -> Tuple[np.ndarray, Dict]:
        """
        Apply dynamic range compression for loudness consistency.
        
        Args:
            audio: Audio signal
            sr: Sample rate
            
        Returns:
            Tuple of (compressed_audio, metadata)
        """
        # Convert threshold to linear
        threshold_linear = 10 ** (self.threshold_db / 20.0)
        
        # Calculate envelope
        attack_samples = int(self.attack_ms * sr / 1000)
        release_samples = int(self.release_ms * sr / 1000)
        
        # Apply compression
        output = audio.copy()
        
        for i in range(len(audio)):
            if np.abs(audio[i]) > threshold_linear:
                # Above threshold: apply compression
                overshoot_db = 20 * np.log10(np.abs(audio[i]) / threshold_linear)
                gain_reduction_db = -overshoot_db * (1 - 1/self.ratio)
                gain_linear = 10 ** (gain_reduction_db / 20.0)
                output[i] = audio[i] * gain_linear
        
        metadata = {
            'method': 'Compressive',
            'threshold_db': self.threshold_db,
            'ratio': self.ratio,
            'attack_ms': self.attack_ms,
            'release_ms': self.release_ms,
            'original_peak_db': float(20 * np.log10(np.max(np.abs(audio)) + 1e-10)),
            'compressed_peak_db': float(20 * np.log10(np.max(np.abs(output)) + 1e-10)),
        }
        
        return output, metadata
