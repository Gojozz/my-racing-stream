function loadCarModel(scene, onLoaded) {
  if (typeof THREE === 'undefined' || typeof THREE.GLTFLoader === 'undefined') return;
  const loader = new THREE.GLTFLoader();
  const cacheBuster = '?v=' + new Date().getTime();

  loader.load('assets/car.glb' + cacheBuster, function (gltf) {
    const car = gltf.scene;
    const scale = 0.002;
    car.scale.set(scale, scale, scale);
    car.position.set(0, 0, 0);

    car.traverse(function (child) {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
      }
    });
    scene.add(car);
    if (typeof onLoaded === 'function') onLoaded(car);
  });
}
