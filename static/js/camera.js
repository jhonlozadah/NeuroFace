function initCamera(videoId, canvasId, captureBtnId, hiddenInputId, previewImgId) {
  const video = document.getElementById(videoId);
  const canvas = document.getElementById(canvasId);
  const captureBtn = captureBtnId ? document.getElementById(captureBtnId) : null;
  const hiddenInput = hiddenInputId ? document.getElementById(hiddenInputId) : null;
  const previewImg = previewImgId ? document.getElementById(previewImgId) : null;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Tu navegador no soporta acceso a la cámara.");
    return;
  }

  navigator.mediaDevices
    .getUserMedia({ video: true, audio: false })
    .then((stream) => {
      video.srcObject = stream;
      video.play();
    })
    .catch((err) => {
      console.error("Error al acceder a la cámara:", err);
      alert("No se pudo acceder a la cámara. Revisa los permisos.");
    });

  if (captureBtn && hiddenInput) {
  captureBtn.addEventListener("click", () => {
    const context = canvas.getContext("2d");

    // Tamaño original del video
    let width = video.videoWidth || 320;
    let height = video.videoHeight || 240;

    // Limitar a un ancho máximo (por ejemplo 480px)
    const maxWidth = 480;
    if (width > maxWidth) {
      const scale = maxWidth / width;
      width = maxWidth;
      height = height * scale;
    }

    canvas.width = width;
    canvas.height = height;
    context.drawImage(video, 0, 0, width, height);

    // Exportar en JPEG con calidad 0.7 en lugar de PNG
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    hiddenInput.value = dataUrl;

    if (previewImg) {
      previewImg.src = dataUrl;
      previewImg.classList.remove("d-none");
    }

    alert("Foto capturada correctamente.");
  });
}
}
