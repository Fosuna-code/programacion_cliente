# Que concepto corregi despues de la implementacion? 
Lo que corregi fue basicamente el entendimiento de la libreria asyncio, pensaba que la funcion gather ejecutaba
una tarea y luego se pasaba a la otra una vez la primera terminara, pero no, ejecuta una y cuando se pone en 
espera, ejecuta la otra y asi sucesivamente
