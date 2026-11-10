# 자문패스 레슨 그림

`pics.js` 는 자문패스 아티팩트(https://claude.ai/artifact/MVb9wb2TW1f1UjqrM9rvGL)에 붙일 레슨 그림 엔진이다.
마스터로드·펀드로드 백과와 같은 토스풍 3D 일러스트를 쓰고, `JP_PICS[레슨 id]` 에 그림 블록(ex·flow·chain·cards)을 넣는다.

붙이는 법(네트워크 접근이 켜진 세션에서):
1. 아티팩트에 `pics.js` 파일을 추가하고 index.html 의 `<script src="data-fund.js"></script>` 앞에 `<script src="pics.js"></script>` 를 넣는다.
2. 레슨 화면의 `<div class="sect" id="s-concept"><h4>개념</h4>` 바로 뒤에 `${window.JP_PIC ? window.JP_PIC(l.id) : ""}` 를 넣는다.

현재 그림이 있는 레슨: 펀드투자권유자문인력 fL1~fL9.
