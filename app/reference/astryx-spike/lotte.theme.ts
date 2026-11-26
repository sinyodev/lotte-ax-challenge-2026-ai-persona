// The lotte theme. `astryx experimental theme editor` wrote this file once and never changes it again.
// The checked settings live in lotte.settings.json and the generated lotte.settings.ts;
// change them with `astryx experimental theme editor set lotte ...`. Add your own changes below: they win over the settings.
import {defineTheme} from '@astryxdesign/core/theme';
import {lotteSettings} from './lotte.settings';

export const lotteTheme = defineTheme({
  extends: lotteSettings,
  name: 'lotte',
});
