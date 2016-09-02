function increment(myInput) {
  myInput.value = (+myInput.value + 1) || 0;
}
function decrement(myInput) {
  myInput.value = (myInput.value - 1) || 0;
}