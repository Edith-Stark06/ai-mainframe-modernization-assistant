import streamlit as st
import streamlit.components.v1 as components

html = """
<div style="background: red; height: 3000px; width: 100%;">
    <h1 style="position: fixed; top: 10px; left: 10px; color: white;">Hello</h1>
</div>
<script>
    const iframe = window.frameElement;
    if (iframe) {
        iframe.style.position = 'fixed';
        iframe.style.top = '0';
        iframe.style.left = '0';
        iframe.style.width = '100vw';
        iframe.style.height = '100vh';
        iframe.style.zIndex = '999999';
        iframe.style.border = 'none';
    }
</script>
"""

st.title("Main Streamlit App")
components.html(html, height=0, scrolling=True)
