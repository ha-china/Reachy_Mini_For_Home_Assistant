import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';

export default {
  input: 'src/reachy-mini-3d-card.js',
  output: {
    file: 'reachy-mini-3d-card.js',
    format: 'iife',
    name: 'ReachyMini3DCard',
    sourcemap: true
  },
  plugins: [
    resolve({
      browser: true,
      preferBuiltins: false
    }),
    commonjs(),
    terser({
      keep_classnames: true,
      keep_fnames: false
    })
  ]
};
